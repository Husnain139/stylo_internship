"""HTTP API for the policy assistant. The screen talks only to these routes."""

from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .access import AUDIENCE_LABELS, AUDIENCES, allowed_audiences, role_label
from .config import BACKEND_ROOT, UNAVAILABLE
from .passwords import hash_password, verify_password
from .factory import build_pipeline
from .ingest import (
    find_policy_file,
    folder_filenames,
    make_chunks,
    read_upload,
    remove_policy_files,
    replacement_policy,
    write_policy_file,
)
from .models import Employee, PolicyDraft
from .pipeline import Pipeline

logger = logging.getLogger("hr_desk")
logging.basicConfig(level=logging.INFO)
_POLICY_ID = re.compile(r"^(?:doc|upload)-[a-f0-9]{16}$")

_LAST_RUN = Path(__file__).resolve().parents[1] / "evals" / "last_run.json"


class SessionIn(BaseModel):
    email: str = ""
    password: str = ""


class SignUpIn(BaseModel):
    email: str = ""
    password: str = ""


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
        return {"me": _person(me) if me else None}

    @app.post("/api/sign-up")
    def sign_up(request: Request, payload: SignUpIn):
        email = payload.email.strip().lower()
        password = payload.password
        if not email or len(password) < 8:
            raise HTTPException(400, "Enter your email and a password of at least 8 characters.")
        store = request.app.state.store
        employee = store.employee(email)
        if not employee:
            raise HTTPException(400, "This email is not on the employee list.")
        if store.password_hash(email):
            raise HTTPException(400, "This email already has a password. Sign in.")
        if not store.set_password(email, hash_password(password)):
            raise HTTPException(400, "This email already has a password. Sign in.")
        return _session_response(store, employee)

    @app.post("/api/session")
    def sign_in(request: Request, payload: SessionIn):
        email = payload.email.strip().lower()
        password = payload.password
        if not email or not password:
            raise HTTPException(400, "Enter your email and password.")
        store = request.app.state.store
        employee = store.employee(email)
        stored = store.password_hash(email) if employee else None
        if not employee or not stored or not verify_password(password, stored):
            raise HTTPException(400, "The email or password does not match.")
        return _session_response(store, employee)

    @app.post("/api/sign-out")
    def sign_out(request: Request):
        token = request.cookies.get("hr_session", "")
        if token:
            request.app.state.store.delete_session(token)
        response = JSONResponse({"ok": True})
        response.delete_cookie("hr_session", path="/")
        return response

    @app.get("/api/media/{policy_id}/{name}")
    def media(request: Request, policy_id: str, name: str):
        employee = _require(request)
        if "/" in policy_id or "/" in name or ".." in name:
            raise HTTPException(404, "That picture is not available.")
        store = request.app.state.store
        policy = next((item for item in store.list_policies() if item.id == policy_id), None)
        if policy is None or policy.audience not in allowed_audiences(employee.designation):
            raise HTTPException(404, "That picture is not available.")
        root = (BACKEND_ROOT / "data" / "policy_media").resolve()
        path = (root / policy_id / name).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(404, "That picture is not available.")
        return FileResponse(path)

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
        _require_admin(request)
        names = folder_filenames()
        rows = [_policy_row(policy, names) for policy in request.app.state.store.list_policies()]
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
        _require_admin(request)
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
        source_name = ""
        if file is not None and (file.filename or ""):
            source_name = Path(file.filename or "").name
            payload = await file.read()
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
            body=body,
            source_name=source_name,
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
            "policy": _policy_row(policy),
        }

    @app.delete("/api/policies/{policy_id}")
    def delete_policy(policy_id: str, request: Request):
        _require_admin(request)
        store = request.app.state.store
        if not _POLICY_ID.fullmatch(policy_id) or not store.has_policy(policy_id):
            raise HTTPException(404, "That policy is no longer in the list.")
        remove_policy_files(policy_id)
        store.delete_policy(policy_id)
        return {"message": "Deleted that policy. People can no longer ask about it."}

    @app.post("/api/policies/{policy_id}")
    async def replace_policy(
        policy_id: str,
        request: Request,
        title: str = Form(""),
        audience: str = Form(""),
        starts_on: str = Form(""),
        text: str = Form(""),
        file: UploadFile | None = File(None),
    ):
        _require_admin(request)
        store = request.app.state.store
        if not _POLICY_ID.fullmatch(policy_id) or not store.has_policy(policy_id):
            raise HTTPException(404, "That policy is no longer in the list.")
        name, chosen, effective_from, body, filename, payload = await _policy_submission(
            title, audience, starts_on, text, file
        )
        previous = find_policy_file(policy_id)
        try:
            draft, stored = replacement_policy(name, chosen, effective_from, body, filename, payload, previous)
        except ValueError as exc:
            if str(exc) == "empty":
                raise HTTPException(400, "Add the policy text or choose a file.") from exc
            raise HTTPException(400, "We couldn't read that file. Paste the policy text instead.") from exc
        if not draft.chunks:
            raise HTTPException(400, "Add the policy text or choose a file.")
        if draft.id != policy_id and store.has_policy(draft.id):
            raise HTTPException(400, "That file is already in the library.")
        pipeline = request.app.state.pipeline
        try:
            vectors = pipeline.embedder.embed([chunk.embed_text for chunk in draft.chunks])
        except Exception as exc:
            logger.exception("Could not embed replacement policy")
            raise HTTPException(500, UNAVAILABLE) from exc
        if stored is not None:
            try:
                write_policy_file(stored, payload)
            except Exception as exc:
                logger.exception("Could not store replacement file")
                raise HTTPException(500, UNAVAILABLE) from exc
        remove_policy_files(policy_id, keep_file=stored, keep_media=draft.id == policy_id)
        store.delete_policy(policy_id)
        try:
            pipeline.store.insert_policy(draft, draft.chunks, vectors)
        except Exception as exc:
            logger.exception("Could not replace policy")
            raise HTTPException(500, UNAVAILABLE) from exc
        return {
            "message": f"Replaced {draft.title}. People who can see it can ask about the new text now.",
            "policy": _policy_row(draft),
        }

    @app.get("/api/questions")
    def questions(request: Request):
        _require_admin(request)
        return {"questions": [_question_row(trace) for trace in request.app.state.store.list_traces()]}

    @app.get("/api/checks")
    def checks(_request: Request):
        _require_admin(_request)
        return _read_checks()


def _current(request: Request) -> Employee | None:
    token = request.cookies.get("hr_session", "")
    return request.app.state.store.employee_for_session(token)


def _require(request: Request) -> Employee:
    employee = _current(request)
    if not employee:
        raise HTTPException(401, "Choose who you are to continue.")
    return employee


def _require_admin(request: Request) -> Employee:
    employee = _require(request)
    if not employee.is_admin:
        raise HTTPException(403, "This page is for an admin.")
    return employee


def _policy_row(policy: PolicyDraft, filenames: dict[str, str] | None = None) -> dict:
    filename = (filenames or {}).get(policy.id) or Path(policy.source_name).name
    if filename in {"", ".", ".."}:
        filename = ""
    return {
        "id": policy.id,
        "title": policy.title,
        "audience": policy.audience,
        "who": AUDIENCE_LABELS.get(policy.audience, policy.audience),
        "starts_on": policy.effective_from.isoformat(),
        "ends_on": policy.effective_to.isoformat() if policy.effective_to else None,
        "filename": filename,
    }


async def _policy_submission(
    title: str,
    audience: str,
    starts_on: str,
    text: str,
    file: UploadFile | None,
) -> tuple[str, str, date, str, str, bytes]:
    name = title.strip()
    if not name:
        raise HTTPException(400, "Give this policy a name.")
    if audience not in AUDIENCES:
        raise HTTPException(400, "Choose who can see this policy.")
    try:
        effective_from = date.fromisoformat(starts_on)
    except ValueError as exc:
        raise HTTPException(400, "Choose the date this policy starts.") from exc
    filename = ""
    payload = b""
    if file is not None and (file.filename or ""):
        filename = file.filename or ""
        payload = await file.read()
    body = text.strip()
    if not payload and not body:
        raise HTTPException(400, "Add the policy text or choose a file.")
    return name, audience, effective_from, body, filename, payload


def _session_response(store, employee: Employee):
    token = store.create_session(employee.email)
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


def _person(employee: Employee) -> dict:
    return {
        "email": employee.email,
        "name": employee.name,
        "designation": employee.designation,
        "role": role_label(employee.designation),
        "isAdmin": employee.is_admin,
    }


def _public_citations(result) -> list[dict]:
    if result.outcome != "answered":
        return []
    merged: list[dict] = []
    index: dict[str, int] = {}
    for item in result.citations:
        if item.image:
            merged.append({"label": item.label, "text": item.text, "image": item.image})
        elif item.label in index:
            merged[index[item.label]]["text"] += "\n\n" + item.text
        else:
            index[item.label] = len(merged)
            merged.append({"label": item.label, "text": item.text, "image": ""})
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
