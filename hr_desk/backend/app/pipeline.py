"""One question, from the guardrails through a saved answer or a fresh one."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import date

from .access import AUDIENCES, access_key, allowed_audiences
from .config import (
    CACHE_SIMILARITY,
    REFUSAL,
    ROLE_REFUSAL,
    UNAVAILABLE,
    UNKNOWN,
    answer_max_tokens,
)
from .guardrails import check_question
from .models import AskResult, Citation, Employee, TraceRecord
from .prompting import prompt_version, system_prompt
from .retrieve import search_passages, select_passages
from .rewrite import recent_history, rewrite_question
from .router import choose_model
from .sanitize import sanitize
from .store_memory import utc_now

logger = logging.getLogger("hr_desk")


class Pipeline:
    def __init__(self, store, embedder, llm, today=None) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.today = today or date.today

    def ask(self, employee: Employee, question: str, history: list[dict] | None = None) -> AskResult:
        started = time.perf_counter()
        state = {
            "guardrail": "pass",
            "guardrail_reason": "ok",
            "classifier_called": False,
            "cache": "skipped",
            "rewritten_question": "",
            "history_note": "",
            "search": "skipped",
            "sections": [],
            "withheld": False,
            "scores": [],
            "model": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "outcome": "error",
            "answer": UNAVAILABLE,
            "citations": [],
        }
        try:
            decision = check_question(question)
            if decision.action in {"block", "pay"}:
                state["guardrail"] = "blocked"
                state["guardrail_reason"] = decision.reason
                state["outcome"] = "refused" if decision.action == "pay" else "blocked"
                state["answer"] = decision.answer
                return self._finish(employee, question, state, started)
            if decision.action == "unsure":
                state["classifier_called"] = True
                verdict = self.llm.classify(question)
                if verdict != "allow":
                    state["guardrail"] = "blocked"
                    state["guardrail_reason"] = "classifier"
                    state["outcome"] = "blocked"
                    state["answer"] = REFUSAL
                    return self._finish(employee, question, state, started)
            if self.llm.moderate(question):
                state["guardrail"] = "blocked"
                state["guardrail_reason"] = "moderation"
                state["outcome"] = "blocked"
                state["answer"] = REFUSAL
                return self._finish(employee, question, state, started)

            turns = recent_history(history or [])
            rewrite = rewrite_question(question, turns)
            if rewrite.needs_model:
                state["rewritten_question"] = self.llm.rewrite(question, turns) or question.strip()
                state["history_note"] = "model"
                background = ""
            else:
                state["rewritten_question"] = rewrite.search_query
                state["history_note"] = rewrite.note
                background = rewrite.background

            embedding = self.embedder.embed([state["rewritten_question"]])[0]
            version = self.store.policy_version()
            key = access_key(employee.designation)
            cached = self.store.cache_lookup(embedding, key, version, CACHE_SIMILARITY)
            state["cache"] = "hit" if cached else "miss"
            if cached:
                state["outcome"] = cached["outcome"]
                state["answer"] = cached["answer"]
                state["citations"] = [
                    Citation(item["label"], item["text"]) for item in (cached["citations"] or [])
                ]
                state["sections"] = [item.label for item in state["citations"]]
                return self._finish(employee, question, state, started)

            audiences = set(allowed_audiences(employee.designation))
            today = self.today()
            passages = search_passages(
                self.store, embedding, state["rewritten_question"], audiences, today
            )
            state["search"] = "done"
            if passages:
                chosen = select_passages(passages)
                state["sections"] = [passage.section_label for passage in chosen]
                state["scores"] = [
                    {"label": passage.section_label, "score": round(passage.score, 3)}
                    for passage in chosen
                ]
                model = choose_model(question, chosen)
                completion = self.llm.answer(
                    system=system_prompt(today),
                    question=question.strip(),
                    background=background,
                    passages=chosen,
                    model=model,
                    max_tokens=answer_max_tokens(model),
                )
                state["model"] = model
                state["tokens_in"] = completion.tokens_in
                state["tokens_out"] = completion.tokens_out
                allowed_numbers = " ".join(
                    [
                        today.isoformat(),
                        *(passage.effective_from.isoformat() for passage in chosen),
                        *(
                            passage.effective_to.isoformat()
                            for passage in chosen
                            if passage.effective_to
                        ),
                    ]
                )
                answer = sanitize(
                    completion.text,
                    [passage.body for passage in chosen],
                    allowed_numbers,
                )
                if answer == REFUSAL:
                    state["outcome"] = "refused"
                    state["answer"] = REFUSAL
                elif answer == UNKNOWN:
                    state["outcome"] = "dont_know"
                    state["answer"] = UNKNOWN
                else:
                    state["outcome"] = "answered"
                    state["answer"] = answer
                    state["citations"] = [Citation(passage.section_label, passage.body) for passage in chosen]
            else:
                everywhere = search_passages(
                    self.store,
                    embedding,
                    state["rewritten_question"],
                    set(AUDIENCES),
                    today,
                )
                hidden = [passage for passage in everywhere if passage.audience not in audiences]
                if hidden:
                    state["withheld"] = True
                    state["outcome"] = "refused"
                    state["answer"] = ROLE_REFUSAL
                else:
                    state["outcome"] = "dont_know"
                    state["answer"] = UNKNOWN

            if state["outcome"] != "error":
                self.store.cache_store(
                    {
                        "id": uuid.uuid4().hex,
                        "embedding": embedding,
                        "access_key": key,
                        "policy_version": version,
                        "question": state["rewritten_question"],
                        "answer": state["answer"],
                        "citations": [
                            {"label": item.label, "text": item.text} for item in state["citations"]
                        ],
                        "outcome": state["outcome"],
                    }
                )
        except Exception:
            logger.exception("Policy question failed")
            state["outcome"] = "error"
            state["answer"] = UNAVAILABLE
            state["citations"] = []
        return self._finish(employee, question, state, started)

    def _finish(self, employee: Employee, question: str, state: dict, started: float) -> AskResult:
        stopped = state["guardrail"] == "blocked"
        trace = TraceRecord(
            id=uuid.uuid4().hex,
            created_at=utc_now(),
            email=employee.email,
            name=employee.name,
            designation=employee.designation,
            question=(question or "").strip(),
            guardrail=state["guardrail"],
            guardrail_reason=state["guardrail_reason"],
            classifier_called=state["classifier_called"],
            cache=state["cache"],
            rewritten_question=state["rewritten_question"],
            history_note=state["history_note"],
            search=state["search"],
            sections=list(state["sections"]),
            withheld=state["withheld"],
            scores=list(state["scores"]),
            model=state["model"],
            tokens_in=state["tokens_in"],
            tokens_out=state["tokens_out"],
            latency_ms=int((time.perf_counter() - started) * 1000),
            outcome=state["outcome"],
            answer=state["answer"],
            citations=list(state["citations"]) if state["outcome"] == "answered" else [],
            steps=plain_steps(
                stopped=stopped,
                cache=state["cache"],
                search=state["search"],
                sections=state["sections"] if state["outcome"] == "answered" else [],
                withheld=state["withheld"],
                model=state["model"],
            ),
            prompt_version=prompt_version(),
        )
        if state["outcome"] != "answered":
            trace.citations = []
        try:
            self.store.add_trace(trace)
        except Exception:
            logger.exception("Could not store the question trace")
        shown = trace.citations if state["outcome"] == "answered" else []
        return AskResult(trace.answer, state["outcome"], shown, trace.id)


def plain_steps(
    *,
    stopped: bool,
    cache: str,
    search: str,
    sections: list[str],
    withheld: bool,
    model: str | None,
) -> list[dict]:
    if cache == "hit":
        saved = "Used a recent similar answer"
    elif cache == "miss":
        saved = "None saved"
    else:
        saved = "Not checked"
    if sections:
        read = "; ".join(dict.fromkeys(sections))
    elif withheld:
        read = "A matching policy is not available for this role"
    elif search == "skipped":
        read = "Not needed"
    else:
        read = "Nothing matched"
    return [
        {"label": "Checked the question", "detail": "Stopped" if stopped else "Allowed"},
        {"label": "Saved answer", "detail": saved},
        {"label": "Read the policies", "detail": read},
        {"label": "Wrote an answer", "detail": "Done" if model else "Not needed"},
    ]
