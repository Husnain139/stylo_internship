"""HTTP API for the policy assistant. The screen talks only to these routes."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .access import AUDIENCE_LABELS, AUDIENCES, PEOPLE, role_label
from .config import UNAVAILABLE
from .factory import build_pipeline
from .ingest import make_chunks, read_upload
from .models import Employee, PolicyDraft
from .pipeline import Pipeline

logger = logging.getLogger("hr_desk")
logging.basicConfig(level=logging.INFO)

_LAST_RUN = Path(__file__).resolve().parents[1] / "evals" / "last_run.json"


class SessionIn(BaseModel):
    email: str = ""


class AskIn(BaseModel):
    question: str = ""
    history: list[dict] = Field(default_factory=list)


def create_app(pipeline: Pipeline | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pipeline is None:
            built = build_pipeline()
        else:
            built = pipeline
        app.state.pipeline = built
        app.state.store = built.store
        yield

    app = FastAPI(title="Stylo HR desk", lifespan=lifespan)
    if pipeline is not None:
        app.state.pipeline = pipeline
        app.state.store = pipeline.store
    register(app)
    return app


def register(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Something went wrong. Try again."
        return JSONResponse(status_code=exc.status_code, content={"message": message})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={"message": "Check the form and try again."},
        )

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception):
        logger.exception("Request failed")
        return JSONResponse(status_code=500, content={"message": UNAVAILABLE, "answer": UNAVAILABLE})

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/bootstrap")
    def bootstrap(request: Request):
        store = request.app.state.store
        me = _current(request)
        return {
            "samples": store.has_samples(),
            "people": [_person(person) for person in _ordered_people(store)],
            "me": _person(me) if me else None,
        }

    @app.post("/api/session")
    def sign_in(request: Request, payload: SessionIn):
        email = payload.email.strip().lower()
        employee = request.app.state.store.employee(email)
        if not employee:
            raise HTTPException(400, "Choose a name from the list.")
        token = request.app.state.store.create_session(email)
        response = JSONResponse({"me": _person(employee)})
        response.set_cookie(
            "hr_session",
            token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=60 * 60 * 12,
        )
        return response

    @app.post("/api/ask")
    def ask(request: Request, payload: AskIn):
        employee = _require(request)
        history = payload.history if isinstance(payload.history, list) else []
        result = request.app.state.pipeline.ask(employee, payload.question, history)
        return {
            "answer": result.answer,
            "outcome": result.outcome,
            "citations": _public_citations(result),
        }

    @app.get("/api/policies")
    def policies(request: Request):
        _require_hr(request)
        rows = []
        for policy in request.app.state.store.list_policies():
            rows.append(
                {
                    "title": policy.title,
                    "audience": policy.audience,
                    "who": AUDIENCE_LABELS.get(policy.audience, policy.audience),
                    "starts_on": policy.effective_from.isoformat(),
                    "ends_on": policy.effective_to.isoformat() if policy.effective_to else None,
                    "sample": policy.sample,
                }
            )
        rows.sort(key=lambda item: (item["title"], item["starts_on"]))
        return {"policies": rows}

    @app.post("/api/policies")
    async def add_policy(
        request: Request,
        title: str = Form(""),
        audience: str = Form(""),
        starts_on: str = Form(""),
        text: str = Form(""),
        file: UploadFile | None = File(None),
    ):
        _require_hr(request)
        name = title.strip()
        if not name:
            raise HTTPException(400, "Give this policy a name.")
        if audience not in AUDIENCES:
            raise HTTPException(400, "Choose who can see this policy.")
        try:
            effective_from = date.fromisoformat(starts_on)
        except ValueError as exc:
            raise HTTPException(400, "Choose the date this policy starts.") from exc
        body = text.strip()
        if file is not None and (file.filename or ""):
            payload = await file.read()
            if len(payload) > 2_000_000:
                raise HTTPException(400, "That file is too big. Use a file under 2 MB.")
            try:
                body = read_upload(file.filename or "", payload)
            except Exception as exc:
                raise HTTPException(400, "We couldn't read that file. Paste the policy text instead.") from exc
        if not body:
            raise HTTPException(400, "Add the policy text or choose a file.")
        policy = PolicyDraft(
            id="upload-" + uuid4().hex[:16],
            title=name,
            audience=audience,
            effective_from=effective_from,
            effective_to=None,
            sample=False,
            body=body,
        )
        chunks = make_chunks(policy)
        if not chunks:
            raise HTTPException(400, "Add the policy text or choose a file.")
        pipeline = request.app.state.pipeline
        try:
            vectors = pipeline.embedder.embed([chunk.embed_text for chunk in chunks])
            pipeline.store.insert_policy(policy, chunks, vectors)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Could not add policy")
            raise HTTPException(500, UNAVAILABLE) from exc
        return {
            "message": f"Added {policy.title}. People who can see it can ask about it now.",
            "policy": {
                "title": policy.title,
                "who": AUDIENCE_LABELS.get(policy.audience, policy.audience),
                "starts_on": policy.effective_from.isoformat(),
                "sample": False,
            },
        }

    @app.get("/api/questions")
    def questions(request: Request):
        _require_hr(request)
        return {"questions": [_question_row(trace) for trace in request.app.state.store.list_traces()]}

    @app.get("/api/checks")
    def checks(_request: Request):
        _require_hr(_request)
        return _read_checks()


def _current(request: Request) -> Employee | None:
    token = request.cookies.get("hr_session", "")
    return request.app.state.store.employee_for_session(token)


def _require(request: Request) -> Employee:
    employee = _current(request)
    if not employee:
        raise HTTPException(401, "Choose who you are to continue.")
    return employee


def _require_hr(request: Request) -> Employee:
    employee = _require(request)
    if employee.designation != "hr":
        raise HTTPException(403, "This page is for HR.")
    return employee


def _ordered_people(store) -> list[Employee]:
    order = {email: index for index, (email, _name, _role) in enumerate(PEOPLE)}
    current = [person for person in store.people() if person.email in order]
    return sorted(current, key=lambda person: order[person.email])


def _person(employee: Employee) -> dict:
    return {
        "email": employee.email,
        "name": employee.name,
        "designation": employee.designation,
        "role": role_label(employee.designation),
    }


def _public_citations(result) -> list[dict]:
    if result.outcome != "answered":
        return []
    merged: list[dict] = []
    index: dict[str, int] = {}
    for item in result.citations:
        if item.label in index:
            merged[index[item.label]]["text"] += "\n\n" + item.text
        else:
            index[item.label] = len(merged)
            merged.append({"label": item.label, "text": item.text})
    return merged


def _question_row(trace) -> dict:
    labels = {
        "answered": "Answered",
        "dont_know": "Could not answer",
        "refused": "Not allowed",
        "blocked": "Not allowed",
        "error": "Could not finish",
    }
    if trace.outcome == "answered" and trace.citations:
        policy = "; ".join(dict.fromkeys(item.label for item in trace.citations))
    elif trace.withheld:
        policy = "Not available for this role"
    elif trace.outcome == "dont_know":
        policy = "No matching policy"
    else:
        policy = "Not answered"
    return {
        "id": trace.id,
        "question": trace.question,
        "asked_by": f"{trace.name}, {role_label(trace.designation)}",
        "outcome_label": labels.get(trace.outcome, "Could not finish"),
        "policy": policy,
        "when": trace.created_at,
        "steps": trace.steps,
        "technical": {
            "model": trace.model,
            "tokens_in": trace.tokens_in,
            "tokens_out": trace.tokens_out,
            "latency_ms": trace.latency_ms,
            "cache": trace.cache,
            "rewritten_question": trace.rewritten_question,
            "history_note": trace.history_note,
            "scores": trace.scores,
            "prompt_version": trace.prompt_version,
            "guardrail_reason": trace.guardrail_reason,
        },
    }


def _read_checks() -> dict:
    if not _LAST_RUN.exists():
        return {
            "status": "missing",
            "summary": "Checks have not been run yet.",
            "ran_at": None,
            "checks": [],
        }
    return json.loads(_LAST_RUN.read_text(encoding="utf-8"))


app = create_app()
