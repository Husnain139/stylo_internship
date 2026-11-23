"""One question, from the guardrails through a saved answer or a fresh one."""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import date

from .access import (
    AUDIENCES,
    access_key,
    grade_band,
    allowed_audiences,
    asks_for_hidden,
    visible_passage,
    names_other_grade,
    policy_row_roles,
    role_reason,
    role_label,
    shares_audience,
)
from .clauses import asked_clause, focus_clauses
from .config import (
    EVIDENCE_MAX_BYTES,
    embed_model,
    model_nano,
    model_mini,
    REFUSAL,
    UNAVAILABLE,
    UNKNOWN,
    answer_max_tokens,
)
from .guardrails import check_question
from .models import AskResult, Citation, Employee, TraceRecord
from .prompting import prompt_version, system_prompt
from .retrieve import search_passages, select_passages
from .rewrite import contextual_query, question_recall, recent_history, rewrite_question, topic_words
from .router import choose_model
from .sanitize import sanitize
from .source_page import source_page_url
from .textutil import token_set
from .store_memory import utc_now

logger = logging.getLogger("hr_desk")

_POLICY_LOCATOR = re.compile(r"\b(?:in|of|under|from)\s+(?:the\s+)?", re.I)
_APPROVAL_REQUEST = re.compile(r"\bwho\b.*\b(?:approve\w*|authori[sz]\w*|sign\w*)\b", re.I)
_APPROVAL_FIELD = re.compile(r"(?:^|[.\n]\s*)(?:competent authority|approving authority|approved by)\s*:", re.I)
_ONE_SENTENCE = re.compile(r"\b(?:one|1|a single)\s+sentence\b", re.I)
_SUMMARY_PREFIX = re.compile(
    r"^(?:(?:in\s+(?:one|1|a single|two|2)\s+sentences?[,\s]+)|"
    r"(?:(?:please\s+)?(?:briefly\s+)?summari[sz]e\s+(?:the\s+)?))+", re.I,
)
_MEDICAL_SCHEDULE = "medical benefit schedule"
_PLAN_ID = re.compile(r"\bplan\s+([a-e])\b", re.I)
_MEDICAL_FIELDS = (
    (r"\b(?:room(?:\s*(?:and|&)\s*board)?(?:\s+(?:rent|limit|charges?))?|board limit)\b", "room & board limit"),
    (r"\b(?:normal|natural)\s+(?:delivery|birth)\b", "normal delivery"),
    (r"\b(?:caesarean|cesarean|c.section|complicated delivery)\b", "complicated /caesarean delivery"),
    (r"\b(?:hospitali[sz]ation|inpatient hospitalization)\b", "hospitalization benefit"),
)
_FOLLOW_FIELD = re.compile(r"^(?:(?:and|also)\b|(?:what|how)\s+about\b)", re.I)
_SELF_ELIGIBILITY = re.compile(r"\b(?:i|my|me)\b.*\b(?:eligible|covered|qualify)\b|\b(?:eligible|covered|qualify)\b.*\b(?:i|my|me)\b", re.I)
_RETAIL_MEDICAL_ROLES = {"senior_store_manager", "store_manager", "assistant_store_manager", "branch_accountant"}


class Pipeline:
    def __init__(self, store, embedder, llm, today=None) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.today = today or date.today #trace

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
            "valid_until": None,
        }
        try:
            decision = check_question(question)
            if decision.action in {"block", "pay"}:
                state["guardrail"] = "blocked"
                state["guardrail_reason"] = decision.reason
                state["outcome"] = "refused" if decision.action == "pay" else "blocked"
                state["answer"] = decision.answer
                return self._finish(employee, question, state, started)
            history = history or []
            ordinal = question_recall(question)
            if ordinal is not None:
                saved = [turn["text"] for turn in history if turn["role"] == "user"]
                if ordinal == -1 and saved:
                    answer = f'Your previous saved question was: "{saved[-1]}"'
                elif 0 < ordinal <= len(saved):
                    answer = f'Question {ordinal} in this chat\'s saved history was: "{saved[ordinal - 1]}"'
                else:
                    answer = "I can't find that question in this chat's saved history."
                state.update(outcome="answered", answer=answer, history_note="question-recall")
                return self._finish(employee, question, state, started)
            grade = grade_band(question)
            grade_question = grade not in {None, "all"} and re.search(
                r"\b(fuel|entitlements?|allowances?|benefits?|coverage|plan|plans|cover|reimbursement)\b",
                question,
                re.IGNORECASE,
            )
            fuel_question = re.search(r"\b(fuel|mileage)\b", question, re.I)
            requested_roles = None
            if fuel_question:
                requested_roles = policy_row_roles("Fuel Entitlement", f"Grade: {question}")
            requested_plan = _medical_plan(question)
            medical_fields = _medical_fields(question)
            if requested_plan:
                requested_roles = policy_row_roles("Medical Benefit Schedule", requested_plan[0])
            if (requested_roles and employee.designation not in requested_roles | {"hr"}
                    or (grade_question and not requested_roles and employee.designation in {"employee", "intern", "trainee"}
                        and employee.designation != grade)):
                state["outcome"] = "refused"
                state["answer"] = "I can't share an entitlement for a different grade. Ask HR if you need help."
                state["withheld"] = True
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
            today = self.today()
            turns = recent_history(history)
            reference = contextual_query(question)
            medical_follow_up = False
            medical_reference = bool(not requested_plan and medical_fields and _FOLLOW_FIELD.match(question.strip()) and not re.search(
                r"\b(?:travel|hotel|accommodation|provident|salary)\b", question, re.I
            ))
            latest_answer = history[-1] if history and history[-1].get("role") == "assistant" else {}
            if (not requested_plan and (reference is not None or medical_reference)
                    and latest_answer.get("outcome") in {"refused", "clarification"}):
                state.update(outcome="clarification", answer="Which policy or plan do you mean?",
                             history_note="follow-up-after-unresolved-turn")
                return self._finish(employee, question, state, started)
            if medical_reference:
                previous, labels = _policy_context(history)
                if labels and all(_MEDICAL_SCHEDULE in label.casefold() for label in labels):
                    medical_follow_up = True
                    requested_plan = _medical_plan(previous)
                    reference = reference or question.strip()
            cacheable = not turns and reference is None and decision.action == "allow"
            question_key = question.strip()
            version = (f"{self.store.policy_version()}:{prompt_version()}:exact-v6:"
                       f"{today.isoformat()}:{embed_model()}:{model_nano()}:{model_mini()}")
            key = access_key(employee.designation)
            cached = self.store.cache_lookup(question_key, key, version) if cacheable else None
            if cacheable:
                state["cache"] = "miss"
            if cached:
                items = cached["citations"] or []
                ids = {item.get("passage_id") for item in items}
                if items and None not in ids:
                    sources = self.store.passages_by_id(list(ids))
                    audiences = set(allowed_audiences(employee.designation))
                    if len(sources) == len(ids) and all(
                        _visible(employee.designation, passage)
                        and shares_audience(passage.audience, audiences)
                        and passage.effective_from <= today
                        and (passage.effective_to is None or passage.effective_to >= today)
                        for passage in sources
                    ):
                        state["valid_until"] = min((p.effective_to for p in sources if p.effective_to), default=None)
                        state["cache"] = "hit"
                        state["outcome"] = cached["outcome"]
                        state["answer"] = cached["answer"]
                        state["citations"] = [
                            Citation(item["label"], item["text"], item.get("image") or "")
                            for item in items
                        ]
                        state["sections"] = [item.label for item in state["citations"]]
                        return self._finish(employee, question, state, started)

            if self.llm.moderate(question):
                state["guardrail"] = "blocked"
                state["guardrail_reason"] = "moderation"
                state["outcome"] = "blocked"
                state["answer"] = REFUSAL
                return self._finish(employee, question, state, started)

            rewrite = rewrite_question(question, turns)
            earlier = _previous_boundary(turns)
            if earlier and not topic_words(question):
                state["history_note"] = "repeat-boundary"
                state["rewritten_question"] = question.strip()
                state["outcome"] = "refused"
                state["answer"] = earlier
                return self._finish(employee, question, state, started)
            policy_ids = None
            approval_rows = []
            answer_question = question.strip()
            named = _named_policy_scope(question, self.store)
            if named:
                subject, policy_ids = named
                subject = _SUMMARY_PREFIX.sub("", subject).strip() or subject
                state.update(rewritten_question=subject, history_note="named-policy")
                background = ""
            elif requested_plan and not medical_follow_up:
                state.update(rewritten_question=question.strip(), history_note="explicit-medical-plan")
                background = ""
            elif reference is not None:
                previous, labels = _policy_context(history)
                policies = self.store.list_policies() if labels else []
                titles = {policy.title for policy in policies if any(
                    label == policy.title or label.startswith((f"{policy.title}, ", f"{policy.title}, p. "))
                    for label in labels
                )}
                if len(titles) != 1:
                    state.update(outcome="clarification", answer="Which policy or topic do you mean?",
                                 history_note="missing-policy-context")
                    return self._finish(employee, question, state, started)
                title = titles.pop()
                policy_ids = [policy.id for policy in policies if policy.title == title]
                state["rewritten_question"] = f"{reference or question.strip()} {title} {previous}".strip()
                state["history_note"] = "policy-follow-up"
                background = previous
                answer_question = f"{reference or question.strip()} under the {title}."
                if _APPROVAL_REQUEST.search(reference):
                    for label in dict.fromkeys(labels):
                        if not label.startswith(f"{title}, "):
                            continue
                        heading = re.sub(r", p\. \d+$", "", label[len(title) + 2:])
                        for policy_id in policy_ids:
                            approval_rows.extend(
                                row for row in self.store.heading_rows(
                                    policy_id, heading, set(allowed_audiences(employee.designation)), today
                                ) if row.content_type == "table" and _APPROVAL_FIELD.search(row.body)
                                and _visible(employee.designation, row)
                            )
            elif rewrite.needs_model:
                rewritten = self.llm.rewrite(question, turns) or question.strip()
                asked = topic_words(question)
                if asked and not asked <= token_set(rewritten):
                    rewritten = f"{rewrite.background} {question}".strip()
                    state["history_note"] = "kept-question"
                else:
                    state["history_note"] = "model"
                state["rewritten_question"] = rewritten
                background = ""
            else:
                state["rewritten_question"] = _SUMMARY_PREFIX.sub("", rewrite.search_query).strip() or rewrite.search_query
                state["history_note"] = rewrite.note
                background = rewrite.background

            audiences = set(allowed_audiences(employee.designation))
            chosen = []
            scope = {} if policy_ids is None else {"policy_ids": policy_ids}
            embedding = None
            medical_lookup = bool(requested_plan or medical_follow_up)
            if medical_lookup:
                passages = [
                    row for row in self.store.heading_hits([_MEDICAL_SCHEDULE], audiences, today, **scope)
                    if row.content_type == "table" and "medical" in row.title.casefold()
                    and _visible(employee.designation, row)
                    and (not requested_plan or _row_plan(row.body) == requested_plan[1].lower())
                ]
            elif approval_rows:
                passages = list({row.id: row for row in approval_rows}.values())
            else:
                embedding = self.embedder.embed([state["rewritten_question"]])[0]
                passages = search_passages(self.store, embedding, state["rewritten_question"], audiences, today, **scope)
            if requested_roles and not medical_lookup:
                passages = [
                    passage for passage in passages if passage.content_type == "table"
                    and "fuel entitlement" in passage.heading.casefold()
                    and (roles := policy_row_roles(passage.heading, passage.body, passage.title))
                    and roles != policy_row_roles("Fuel Entitlement", "Grade: All Levels")
                    and requested_roles <= roles
                ]
            elif grade_question and employee.designation in {"employee", "hr"}:
                matching_rows = [
                    passage for passage in passages
                    if passage.content_type == "table" and grade_band(f"{passage.heading} {passage.body}") == grade
                ]
                if matching_rows:
                    passages = matching_rows
            state["search"] = "done"
            if passages:
                chosen = select_passages(passages)
                probe = state["rewritten_question"] if policy_ids or not topic_words(question) else question
                matched = chosen if medical_lookup else [passage for passage in chosen if asks_for_hidden(probe, [passage])]
                if not matched and not names_other_grade(employee.designation, question):
                    state["outcome"] = "dont_know"
                    state["answer"] = UNKNOWN
                    state["citations"] = []
                    chosen = []
                else:
                    chosen = matched or chosen
                visible = [passage for passage in chosen if _visible(employee.designation, passage)]
                if chosen and not visible:
                    visible_matches = [
                        passage
                        for passage in passages
                        if _visible(employee.designation, passage) and asks_for_hidden(probe, [passage])
                    ]
                    if visible_matches and not names_other_grade(employee.designation, question):
                        chosen = select_passages(visible_matches)
                    elif asks_for_hidden(probe, chosen) or names_other_grade(employee.designation, question):
                        state["withheld"] = True
                        state["outcome"] = "refused"
                        state["answer"] = role_reason(employee.designation, chosen)
                        state["sections"] = [passage.section_label for passage in chosen]
                        state["citations"] = []
                        chosen = []
                    else:
                        state["outcome"] = "dont_know"
                        state["answer"] = UNKNOWN
                        state["citations"] = []
                        chosen = []
                else:
                    chosen = visible
                if state["outcome"] != "refused":
                    focused = focus_clauses(chosen, question)
                    if focused is not None:
                        chosen = focused
                        titles = list(dict.fromkeys(passage.title for passage in chosen))
                        if len(titles) > 1:
                            options = ", ".join(titles)
                            state["outcome"] = "clarification"
                            state["answer"] = f"Which policy do you mean for point {asked_clause(question)}? I found it in {options}."
                            return self._finish(employee, question, state, started)
                        if not chosen:
                            state["outcome"] = "dont_know"
                            state["answer"] = UNKNOWN
                    state["sections"] = [passage.section_label for passage in chosen]
                state["scores"] = [
                    {"label": passage.section_label, "score": round(passage.score, 3)}
                    for passage in chosen
                ]
                if chosen and all(passage.content_type == "table" for passage in chosen):
                    state["outcome"] = "answered"
                    state["answer"] = friendly_table(chosen)
                    if medical_lookup and medical_fields:
                        state["answer"] = _medical_field_answer(chosen, medical_fields, question)
                        if state["answer"] == UNKNOWN:
                            state["outcome"] = "dont_know"
                    if fuel_question and len(chosen) > 1 and all(
                        "fuel entitlement" in passage.heading.casefold() for passage in chosen
                    ) and sum(
                        employee.designation in (policy_row_roles(passage.heading, passage.body, passage.title) or set())
                        and "all levels" not in passage.body.casefold() for passage in chosen
                    ) > 1:
                        state["answer"] = "The policy lists more than one row for your designation. Ask HR which one applies.\n\n" + state["answer"]
                    if len(chosen) == 1 and approval_rows:
                        fields = dict(_fields(chosen[0].body))
                        approver = next((value for name, value in fields.items() if _APPROVAL_FIELD.search(f"{name}:")), "")
                        if approver:
                            state["answer"] = f"{approver} must approve the request."
                    elif approval_rows:
                        state["answer"] = "The approver depends on the designation:\n\n" + state["answer"]
                    if state["outcome"] == "answered":
                        state["citations"] = [_citation(passage, employee.designation == "hr") for passage in chosen]
                elif chosen:
                    direct_answer = (
                        _retail_eligibility(employee.designation, question, chosen)
                        or _travel_authorization_summary(question, chosen)
                    )
                    if direct_answer:
                        state.update(outcome="answered", answer=_short_answer(direct_answer, question),
                                     citations=[_citation(passage) for passage in chosen])
                        state["valid_until"] = min((p.effective_to for p in chosen if p.effective_to), default=None)
                        return self._finish(employee, question, state, started)
                    evidence = []
                    remaining = EVIDENCE_MAX_BYTES
                    for passage in chosen:
                        size = len(f"{passage.section_label}\n{passage.body}".encode("utf-8")) + 80
                        if size > remaining:
                            break
                        remaining -= size
                        evidence.append(passage)
                    if not evidence:
                        raise RuntimeError("Policy evidence exceeds the request budget")
                    chosen = evidence
                    model = choose_model(question, chosen)
                    completion = self.llm.answer(
                        system=system_prompt(today),
                        question=answer_question,
                        background=background,
                        passages=chosen,
                        model=model,
                        max_tokens=answer_max_tokens(model),
                        designation=role_label(employee.designation),
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
                    missed = "I couldn't find this in the policies I can open."
                    if answer.strip() == missed:
                        answer = UNKNOWN
                    elif missed in answer and answer.strip() != UNKNOWN:
                        answer = " ".join(answer.replace(UNKNOWN, "").replace(missed, "").split()) or UNKNOWN
                    if answer == UNKNOWN and named and _ONE_SENTENCE.search(question) and _SUMMARY_PREFIX.match(question):
                        answer = _named_summary_excerpt(state["rewritten_question"], chosen)
                    answer = _short_answer(answer, question)
                    if answer == REFUSAL:
                        state["outcome"] = "refused"
                        state["answer"] = REFUSAL
                    elif answer == UNKNOWN:
                        state["outcome"] = "dont_know"
                        state["answer"] = UNKNOWN
                    else:
                        state["outcome"] = "answered"
                        state["answer"] = answer
                        state["citations"] = [_citation(passage, employee.designation == "hr") for passage in chosen]
            elif policy_ids is None and embedding is not None:
                everywhere = search_passages(
                    self.store,
                    embedding,
                    state["rewritten_question"],
                    set(AUDIENCES),
                    today,
                )
                hidden = [passage for passage in everywhere if not shares_audience(passage.audience, audiences) or not _visible(employee.designation, passage)]
                if hidden and asks_for_hidden(question, hidden):
                    state["withheld"] = True
                    state["outcome"] = "refused"
                    state["answer"] = role_reason(employee.designation, hidden)
                else:
                    state["outcome"] = "dont_know"
                    state["answer"] = UNKNOWN
            else:
                state.update(outcome="dont_know", answer=UNKNOWN)

            if state["outcome"] == "answered":
                if re.search(r"\b(link|url|form|submit|apply|file|claim)\b", question, re.I):
                    state["answer"] = with_passage_links(state["answer"], chosen)
                state["valid_until"] = min((p.effective_to for p in chosen if p.effective_to), default=None)
            if cacheable and state["outcome"] == "answered" and state["citations"]:
                try:
                    self.store.cache_store(
                        {
                            "id": uuid.uuid4().hex,
                            "access_key": key,
                            "policy_version": version,
                            "question": question_key,
                            "answer": state["answer"],
                            "citations": [
                                {"label": item.label, "text": item.text, "image": item.image,
                                 "passage_id": passage.id}
                                for item, passage in zip(state["citations"], chosen)
                            ],
                            "outcome": state["outcome"],
                        }
                    )
                except Exception:
                    logger.warning("Could not store answer cache entry", exc_info=True)
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
            question=(question or "").strip()[:1000] if not stopped else "",
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
        return AskResult(trace.answer, state["outcome"], shown, trace.id, state["valid_until"])


def _medical_plan(question: str) -> re.Match | None:
    match = re.search(
        r"\bplan\s+([a-e])(?=\s*[?.!,]*$|\s+(?:coverage|benefits?|cover|in)\b)", question, re.I,
    )
    if match or re.search(r"\b(medical|takaful|hospital|insurance)\b", question, re.I) or _medical_fields(question):
        return match or _PLAN_ID.search(question)
    return None


def _row_plan(body: str) -> str:
    match = re.match(r"(?:plan:\s*)?plan\s+([a-e])\b", body.strip(), re.I)
    return match[1].lower() if match else ""


def _medical_fields(question: str) -> list[str]:
    return [label for pattern, label in _MEDICAL_FIELDS if re.search(pattern, question, re.I)]


def _medical_field_answer(passages, requested: list[str], question: str) -> str:
    values = {}
    for passage in passages:
        plan = _row_plan(passage.body)
        for name, value in _fields(passage.body):
            key = name.casefold()
            if any(key.startswith(field) for field in requested):
                values.setdefault((plan, name), set()).add(value)
    if not values:
        return UNKNOWN
    if len(values) == 1:
        (_, name), amounts = next(iter(values.items()))
        if len(amounts) == 1:
            amount = next(iter(amounts))
            if re.search(r"\b(?:just|only)\s+(?:the\s+)?amount\b|\bamount\s+only\b", question, re.I):
                return amount
            return f"{name}: {amount}."
    if any(len(amounts) > 1 for amounts in values.values()):
        return "The policy gives conflicting amounts. Please check with HR."
    return _markdown_table(["Plan", "Benefit", "Amount"], [
        [f"Plan {plan.upper()}", name, next(iter(amounts))] for (plan, name), amounts in values.items()
    ])


def _retail_eligibility(designation: str, question: str, passages) -> str:
    if (designation not in _RETAIL_MEDICAL_ROLES or not _SELF_ELIGIBILITY.search(question)
            or not re.search(r"\b(?:medical|takaful|health insurance)\b", question, re.I)
            or re.search(r"\b(?:maternity|dependents?|spouse|children|exclusions?|plan)\b", question, re.I)):
        return ""
    role = role_label(designation)
    for passage in passages:
        if ("medical" in passage.title.casefold() and "permanent management employees" in passage.body.casefold()
                and re.search(rf"\b{re.escape(role)}s?\b", passage.body, re.I)):
            return f"Yes, if you're a permanent employee. The policy lists {role} as an eligible designation."
    return ""


def _travel_authorization_summary(question: str, passages) -> str:
    if not re.search(r"\b(?:authori[sz]ation of (?:business )?travel|travel authori[sz]ation)\b", question, re.I):
        return ""
    if asked_clause(question) or re.search(
        r"\b(?:who|when|where|exceptions?|restrictions?|urgent|sales|audit|form|link|compare|exact)\b", question, re.I,
    ):
        return ""
    text = "\n".join(p.body for p in passages if p.title == "Travel Policy"
                     and p.heading.startswith("3.2.") and p.content_type == "section").casefold()
    deadline = re.search(r"at least (\d+) days prior to the travel date", text)
    required = ("pre-approved by the competent authority", "dually signed travel request form",
                "administration department via hr", "seek approval via email", "upon returning",
                "complete the travel request form", "obtain all necessary approvals")
    if not deadline or not all(phrase in text for phrase in required):
        return ""
    answer = (f"Get pre-approval and send the dually signed Travel Request Form to Administration via HR "
              f"at least {deadline[1]} days before travel. For urgent travel, get email approval and "
              "complete the form and remaining approvals when you return.")
    if all(term in text for term in ("sales staff", "field audit staff", "internal guidelines")):
        answer += " Sales and Field Audit staff follow their own department guidelines."
    return answer


def _named_summary_excerpt(subject: str, passages) -> str:
    """Fallback for an explicitly named public section, when the model yields no answer."""
    terms = lambda text: re.findall(r"\w+", text.casefold())
    sentences = []
    for passage in passages:
        if passage.audience != "everyone" or terms(passage.heading) != terms(subject):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(passage.body.split())):
            if 6 <= len(sentence.split()) <= 42 and sentence.endswith((".", "!", "?")):
                if sanitize(sentence, [passage.body]) == sentence:
                    sentences.append(sentence)
    if not sentences:
        return UNKNOWN
    return min(sentences, key=lambda item: (
        not bool(re.search(r"\b(?:values|purpose|means|requires)\b", item, re.I)),
        bool(re.search(r"\d", item)),
    ))


def _short_answer(answer: str, question: str) -> str:
    lines = []
    seen = set()
    for line in answer.splitlines():
        key = re.sub(r"[^\w]+", " ", line.casefold()).strip()
        if key and not line.lstrip().startswith("|"):
            if key in seen:
                continue
            seen.add(key)
        lines.append(line)
    text = "\n".join(lines).strip()
    if text in {UNKNOWN, REFUSAL}:
        return text
    if not any(line.lstrip().startswith(("-", "|")) for line in lines):
        text = re.sub(r"(?<=[.!?])\s+(?:If you(?:’|'| a)re (?:seeking|looking for)|For (?:the )?(?:full|exact) (?:text|details)).*\Z",
                      "", text, flags=re.I | re.S)
        if _ONE_SENTENCE.search(question):
            # Keep essential exceptions as clauses instead of dropping later sentences.
            text = re.sub(r"(?<![A-Z])(?<!\b[Rr]s)(?<!\b[Nn]o)(?<!\b[Mm]r)(?<!\b[Mm]s)[.!?]\s+(?=[A-Z])",
                          "; ", text)
    return text


def _named_policy_scope(question: str, store) -> tuple[str, list[str]] | None:
    """Separate a section request from a trailing, explicitly named document."""
    matches = list(_POLICY_LOCATOR.finditer(question))
    if not matches:
        return None
    title_key = lambda text: " ".join(re.findall(r"\w+", text.casefold()))
    policies = store.list_policies()
    for match in reversed(matches):
        subject = question[:match.start()].strip(" ,:\t")
        key = title_key(question[match.end():])
        ids = [policy.id for policy in policies if title_key(policy.title) == key]
        if subject and ids:
            return subject, ids
    return None


def _policy_context(history: list[dict]) -> tuple[str, list[str]]:
    previous = ""
    labels = []
    for index in range(len(history) - 1, 0, -2):
        asked, answer = history[index - 1:index + 1]
        if asked["role"] != "user" or answer["role"] != "assistant" or question_recall(asked["text"]) is not None:
            continue
        if answer.get("outcome") in {"refused", "clarification"}:
            break
        if not previous:
            # The latest topic must have sources. Never jump across an unanswered topic.
            labels = [item["label"] for item in answer.get("citations", []) if item.get("label")]
            if not labels:
                break
            previous = asked["text"]
        medical_continuation = bool(
            _FOLLOW_FIELD.match(asked["text"]) and _medical_fields(asked["text"]) and not _medical_plan(asked["text"])
            and any(_MEDICAL_SCHEDULE in label.casefold() for label in labels)
        )
        if contextual_query(asked["text"]) is None and not medical_continuation:
            previous = asked["text"]
            break
    return previous, labels


def _previous_boundary(turns: list[dict]) -> str:
    """The last answer, when it was a role boundary rather than a policy answer."""
    for turn in reversed(turns):
        if turn.get("role") != "assistant":
            continue
        text = (turn.get("text") or "").strip()
        if text.startswith("I can't share") or text.startswith("I can't answer"):
            return text
        return ""
    return ""


def _visible(designation: str, passage) -> bool:
    return visible_passage(designation, passage)


_LINK = re.compile(r"https?://[^\s)>\]]+")


def _joined_links(text: str) -> str:
    """A web address printed over two lines is one address."""
    lines = (text or "").splitlines()
    joined: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.search(r"https?://\S+$", line) and index + 1 < len(lines):
            nxt = lines[index + 1].strip()
            if nxt and " " not in nxt and not re.match(r"^\d", nxt):
                line = line.rstrip() + nxt
                index += 1
        joined.append(line)
        index += 1
    return "\n".join(joined)


def _link_label(line: str, url: str) -> str:
    before = line.split(url, 1)[0]
    before = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", before.strip())
    before = re.sub(r"\s*please visit\s*$", "", before, flags=re.I)
    before = before.strip(" :.-")
    if ":" in before:
        tail = before.split(":")[-1].strip()
        if tail:
            before = tail
    return before


def with_passage_links(answer: str, passages) -> str:
    """Add each web address from the passages the answer used."""
    text = answer or ""
    found: list[str] = []
    seen = {match.rstrip(".,)") for match in _LINK.findall(text)}
    for passage in passages:
        body = _joined_links(getattr(passage, "body", "") or "")
        for line in body.splitlines():
            for match in _LINK.findall(line):
                url = match.rstrip(".,)")
                if url in seen:
                    continue
                seen.add(url)
                label = _link_label(line, url)
                found.append(f"{label}: {url}" if label else url)
    if not found:
        return text
    return text.rstrip() + "\n\n" + "\n".join(found)


def friendly_table(passages) -> str:
    """Turn table rows into one markdown table so the screen can draw a real table."""
    records = []
    for passage in passages:
        pairs = _fields(passage.body)
        if pairs:
            records.append(pairs)
        elif passage.body.strip():
            records.append([("Details", passage.body.strip())])
    if not records:
        return ""
    labels = [label for label, _ in records[0]]
    same_shape = all([label for label, _ in record] == labels for record in records)
    if len(records) > 1 and same_shape:
        return _markdown_table(labels, [[value for _, value in record] for record in records])
    lines = []
    for record in records:
        lines.append(_markdown_table(["Item", "Details"], [[label, value] for label, value in record]))
    return "\n\n".join(lines)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def cell(value: str) -> str:
        return value.replace("|", "/").replace("\n", " ").strip()

    head = "| " + " | ".join(cell(header) for header in headers) + " |"
    rule = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _fields(body: str) -> list[tuple[str, str]]:
    pairs = []
    for part in re.split(r"(?<!Rs)(?<!Sr)\.\s+", body.strip()):
        piece = part.strip().strip(".")
        if ":" not in piece:
            continue
        label, value = piece.split(":", 1)
        label = label.strip()
        value = value.strip(" .")
        if label and value:
            pairs.append((label, value))
    return pairs


def _citation(passage, include_full_page=False) -> Citation:
    images = []
    if passage.image_path:
        images.extend(f"/api/media/{path}" for path in passage.image_path.split("|")
                      if path and (include_full_page or not path.rsplit("/", 1)[-1].startswith("page-")))
    source = source_page_url(passage) if include_full_page else ""
    if source and source not in images:
        images.append(source)
    label = f"{passage.section_label}, p. {passage.page}" if passage.page else passage.section_label
    return Citation(label, passage.body, "|".join(images))


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
