"""FastAPI routes for the audit document reviewer prototype."""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import rbac
from .audit_log import append_event, event_payload, list_events, utc_now
from .config import model_mode
from .db import connect, init_db
from .service import (
    document_dict,
    engagement_dict,
    field_dict,
    distinct_by_hash,
    findings_payload,
    ingest_bytes,
    list_sample_packs,
    load_documents,
    load_pack_documents,
    new_id,
    run_analysis,
    stored_file,
)

bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: str
    email: str
    name: str
    role: str


class LoginIn(BaseModel):
    email: str
    password: str


class EngagementIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    assign_auditors: bool = False


class MemberIn(BaseModel):
    email: str


class ScopeIn(BaseModel):
    audit_type: str | None = None


class RejectScopeIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class ReviewIn(BaseModel):
    action: str
    note: str | None = None


class UserIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=120)
    role: str
    password: str = Field(min_length=8, max_length=200)


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None


class RetentionIn(BaseModel):
    retention_days: int = Field(ge=1, le=36500)
    legal_hold: bool = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Audit Document Reviewer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Sign in required")
    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND users.active = 1
            """,
            (token_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return CurrentUser(id=row["id"], email=row["email"], name=row["name"], role=row["role"])


def require(permission: str):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not rbac.allows(user.role, permission):
            raise HTTPException(status_code=403, detail="This role cannot perform that action")
        return user

    return dependency


def member_engagement(conn, engagement_id: str, user: CurrentUser, *, admin_may_read_metadata: bool):
    row = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if admin_may_read_metadata and user.role == rbac.ADMIN:
        return row
    member = conn.execute(
        "SELECT 1 FROM memberships WHERE engagement_id = ? AND user_id = ?",
        (engagement_id, user.id),
    ).fetchone()
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this engagement")
    return row


def _refuse_ingest_when_scope_locked(row) -> None:
    if row["scope_status"] == "rejected":
        raise HTTPException(
            status_code=409,
            detail="Scope is rejected. A senior auditor reopens it before documents can be added",
        )
    if row["scope_status"] == "confirmed":
        raise HTTPException(
            status_code=409,
            detail="Scope is confirmed. A senior auditor reopens it before the file set can change",
        )


def document_for_user(conn, document_id: str, user: CurrentUser):
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    member_engagement(conn, row["engagement_id"], user, admin_may_read_metadata=False)
    return row


@app.get("/health")
def health():
    return {"status": "ok", "model_mode": model_mode()}


@app.post("/auth/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    conn = connect()
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not user["active"] or not rbac.verify_password(body.password, user["password_hash"]):
            append_event(
                conn,
                actor=email or "unknown",
                action="AUTH_FAILED",
                object_type="session",
                object_id=email or "unknown",
                payload={"email": email},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?,?,?)",
            (hashlib.sha256(token.encode("utf-8")).hexdigest(), user["id"], utc_now()),
        )
        append_event(
            conn,
            actor=user["email"],
            action="AUTH_LOGIN",
            object_type="session",
            object_id=user["id"],
            payload={"role": user["role"]},
        )
        return {"token": token, "email": user["email"], "name": user["name"], "role": user["role"]}
    finally:
        conn.close()


@app.post("/auth/logout")
def logout(user: CurrentUser = Depends(get_current_user), credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    conn = connect()
    try:
        if credentials and credentials.credentials:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest(),),
            )
            conn.commit()
        append_event(
            conn,
            actor=user.email,
            action="AUTH_LOGOUT",
            object_type="session",
            object_id=user.id,
            payload={"role": user.role},
        )
        return {"ok": True}
    finally:
        conn.close()


@app.get("/auth/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return user


@app.post("/engagements")
def create_engagement(body: EngagementIn, user: CurrentUser = Depends(require("engagement:create"))):
    engagement_id = new_id()
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO engagements (
              id, name, proposed_reasons, missing_evidence, scope_status, created_by, created_at
            ) VALUES (?, ?, '[]', '[]', 'proposed', ?, ?)
            """,
            (engagement_id, body.name.strip(), user.email, utc_now()),
        )
        conn.execute(
            "INSERT INTO memberships (engagement_id, user_id) VALUES (?, ?)",
            (engagement_id, user.id),
        )
        if body.assign_auditors:
            auditors = conn.execute(
                "SELECT id FROM users WHERE active = 1 AND role IN (?, ?)",
                (rbac.JUNIOR, rbac.SENIOR),
            ).fetchall()
            for auditor in auditors:
                conn.execute(
                    "INSERT OR IGNORE INTO memberships (engagement_id, user_id) VALUES (?, ?)",
                    (engagement_id, auditor["id"]),
                )
        append_event(
            conn,
            actor=user.email,
            action="ENGAGEMENT_CREATED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"name": body.name.strip(), "assign_auditors": body.assign_auditors},
        )
        row = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
        return engagement_dict(row, conn)
    finally:
        conn.close()


@app.get("/engagements")
def list_engagements(user: CurrentUser = Depends(require("engagement:read"))):
    conn = connect()
    try:
        if user.role == rbac.ADMIN:
            rows = conn.execute("SELECT * FROM engagements ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                """
                SELECT engagements.* FROM engagements
                JOIN memberships ON memberships.engagement_id = engagements.id
                WHERE memberships.user_id = ?
                ORDER BY engagements.created_at DESC
                """,
                (user.id,),
            ).fetchall()
        return [engagement_dict(row, conn) for row in rows]
    finally:
        conn.close()


@app.get("/engagements/{engagement_id}")
def get_engagement(engagement_id: str, user: CurrentUser = Depends(require("engagement:read"))):
    conn = connect()
    try:
        row = member_engagement(conn, engagement_id, user, admin_may_read_metadata=True)
        return engagement_dict(row, conn)
    finally:
        conn.close()


@app.post("/engagements/{engagement_id}/members")
def add_member(
    engagement_id: str,
    body: MemberIn,
    user: CurrentUser = Depends(require("member:assign")),
):
    email = body.email.strip().lower()
    conn = connect()
    try:
        member_engagement(conn, engagement_id, user, admin_may_read_metadata=True)
        target = conn.execute("SELECT * FROM users WHERE email = ? AND active = 1", (email,)).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute(
            "INSERT OR IGNORE INTO memberships (engagement_id, user_id) VALUES (?, ?)",
            (engagement_id, target["id"]),
        )
        append_event(
            conn,
            actor=user.email,
            action="MEMBERSHIP_GRANTED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"email": email, "role": target["role"]},
        )
        return {"engagement_id": engagement_id, "email": email, "role": target["role"]}
    finally:
        conn.close()


@app.post("/engagements/{engagement_id}/documents")
async def upload_document(
    engagement_id: str,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require("document:upload")),
):
    payload = await file.read()
    conn = connect()
    try:
        row = member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        _refuse_ingest_when_scope_locked(row)
        return ingest_bytes(
            conn,
            engagement_id=engagement_id,
            filename=file.filename or "document.pdf",
            payload=payload,
            actor=user.email,
        )
    finally:
        conn.close()


@app.get("/sample-packs")
def sample_packs(user: CurrentUser = Depends(require("document:upload"))):
    del user
    return list_sample_packs()


@app.post("/engagements/{engagement_id}/load-samples")
def load_samples(
    engagement_id: str,
    pack: str | None = None,
    user: CurrentUser = Depends(require("document:upload")),
):
    conn = connect()
    try:
        row = member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        _refuse_ingest_when_scope_locked(row)
        loaded = load_pack_documents(conn, engagement_id, user.email, pack)
        return {"pack": pack or "mismatch", "documents": loaded}
    finally:
        conn.close()

@app.get("/engagements/{engagement_id}/documents")
def list_documents(engagement_id: str, user: CurrentUser = Depends(require("document:read"))):
    conn = connect()
    try:
        member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        rows = conn.execute(
            "SELECT * FROM documents WHERE engagement_id = ? ORDER BY uploaded_at",
            (engagement_id,),
        ).fetchall()
        return distinct_by_hash([document_dict(row) for row in rows])
    finally:
        conn.close()


@app.get("/documents/{document_id}/file")
def download_document(
    document_id: str,
    download: int = 0,
    user: CurrentUser = Depends(require("document:read")),
):
    conn = connect()
    try:
        row = document_for_user(conn, document_id, user)
        path = stored_file(row["stored_name"])
        action = "DOCUMENT_DOWNLOADED" if download else "DOCUMENT_VIEWED"
        append_event(
            conn,
            actor=user.email,
            action=action,
            object_type="document",
            object_id=document_id,
            payload={"filename": row["filename"]},
        )
        return FileResponse(path, media_type="application/pdf", filename=row["filename"])
    finally:
        conn.close()


@app.get("/engagements/{engagement_id}/evidence")
def engagement_evidence(engagement_id: str, user: CurrentUser = Depends(require("evidence:read"))):
    conn = connect()
    try:
        member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        documents = load_documents(conn, engagement_id)
        append_event(
            conn,
            actor=user.email,
            action="EVIDENCE_VIEWED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"document_count": len(documents)},
        )
        return {"documents": documents}
    finally:
        conn.close()


@app.get("/documents/{document_id}/evidence")
def document_evidence(document_id: str, user: CurrentUser = Depends(require("evidence:read"))):
    conn = connect()
    try:
        row = document_for_user(conn, document_id, user)
        fields = [
            field_dict(field)
            for field in conn.execute(
                "SELECT * FROM evidence_fields WHERE document_id = ? ORDER BY field_name",
                (document_id,),
            ).fetchall()
        ]
        append_event(
            conn,
            actor=user.email,
            action="EVIDENCE_VIEWED",
            object_type="document",
            object_id=document_id,
            payload={"field_count": len(fields)},
        )
        payload = document_dict(row)
        payload["fields"] = fields
        return payload
    finally:
        conn.close()


@app.post("/engagements/{engagement_id}/confirm-scope")
def confirm_scope(
    engagement_id: str,
    body: ScopeIn,
    user: CurrentUser = Depends(require("scope:confirm")),
):
    conn = connect()
    try:
        row = member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        if row["proposed_type"] != "procurement_financial":
            raise HTTPException(
                status_code=400,
                detail="Classify documents as a procurement pack before confirming scope",
            )
        audit_type = (body.audit_type or row["proposed_type"] or "").strip()
        if audit_type not in {"procurement_financial"}:
            raise HTTPException(
                status_code=400,
                detail="This prototype can confirm only a procurement_financial scope",
            )
        confirmed_at = utc_now()
        conn.execute(
            """
            UPDATE engagements
            SET scope_status = 'confirmed',
                scope_audit_type = ?,
                scope_confirmed_by = ?,
                scope_confirmed_at = ?,
                scope_rejected_by = NULL,
                scope_rejected_at = NULL,
                scope_rejection_note = NULL
            WHERE id = ?
            """,
            (audit_type, user.email, confirmed_at, engagement_id),
        )
        append_event(
            conn,
            actor=user.email,
            action="SCOPE_CONFIRMED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"audit_type": audit_type, "prior_scope_status": row["scope_status"]},
        )
        updated = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
        return engagement_dict(updated, conn)
    finally:
        conn.close()


@app.post("/engagements/{engagement_id}/reject-scope")
def reject_scope(
    engagement_id: str,
    body: RejectScopeIn,
    user: CurrentUser = Depends(require("scope:confirm")),
):
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="A rejection reason is required")
    conn = connect()
    try:
        row = member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        if row["scope_status"] == "confirmed":
            raise HTTPException(
                status_code=409,
                detail="Scope is already confirmed. This prototype does not withdraw a confirmation",
            )
        rejected_at = utc_now()
        conn.execute(
            """
            UPDATE engagements
            SET scope_status = 'rejected',
                scope_audit_type = NULL,
                scope_confirmed_by = NULL,
                scope_confirmed_at = NULL,
                scope_rejected_by = ?,
                scope_rejected_at = ?,
                scope_rejection_note = ?
            WHERE id = ?
            """,
            (user.email, rejected_at, note, engagement_id),
        )
        append_event(
            conn,
            actor=user.email,
            action="SCOPE_REJECTED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"scope_status": "rejected", "note": note, "prior_scope_status": row["scope_status"]},
        )
        updated = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
        return engagement_dict(updated, conn)
    finally:
        conn.close()


@app.post("/engagements/{engagement_id}/reopen-scope")
def reopen_scope(engagement_id: str, user: CurrentUser = Depends(require("scope:confirm"))):
    conn = connect()
    try:
        row = member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        if row["scope_status"] not in {"rejected", "confirmed"}:
            raise HTTPException(
                status_code=409,
                detail="Only a rejected or confirmed scope can be reopened for document changes",
            )
        prior = row["scope_status"]
        conn.execute(
            """
            UPDATE engagements
            SET scope_status = 'proposed',
                scope_audit_type = NULL,
                scope_confirmed_by = NULL,
                scope_confirmed_at = NULL,
                scope_rejected_by = NULL,
                scope_rejected_at = NULL,
                scope_rejection_note = NULL
            WHERE id = ?
            """,
            (engagement_id,),
        )
        append_event(
            conn,
            actor=user.email,
            action="SCOPE_REOPENED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"scope_status": "proposed", "prior_scope_status": prior},
        )
        updated = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
        return engagement_dict(updated, conn)
    finally:
        conn.close()


@app.post("/engagements/{engagement_id}/analyze")
def analyze(engagement_id: str, user: CurrentUser = Depends(require("analysis:run"))):
    conn = connect()
    try:
        member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        return run_analysis(conn, engagement_id, user.email)
    finally:
        conn.close()


@app.get("/engagements/{engagement_id}/findings")
def list_findings(engagement_id: str, user: CurrentUser = Depends(require("finding:read"))):
    conn = connect()
    try:
        member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        payload = findings_payload(conn, engagement_id)
        append_event(
            conn,
            actor=user.email,
            action="FINDINGS_VIEWED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"finding_count": len(payload)},
        )
        return {"findings": payload}
    finally:
        conn.close()


@app.post("/findings/{finding_id}/review")
def review_finding(
    finding_id: str,
    body: ReviewIn,
    user: CurrentUser = Depends(require("finding:review")),
):
    action = body.action.strip().lower()
    status_by_action = {"approve": "approved", "correct": "corrected", "reject": "rejected"}
    event_by_action = {
        "approve": "FINDING_APPROVED",
        "correct": "FINDING_CORRECTED",
        "reject": "FINDING_REJECTED",
    }
    if action not in status_by_action:
        raise HTTPException(status_code=400, detail="Review action must be approve, correct, or reject")
    if action == "correct" and not (body.note and body.note.strip()):
        raise HTTPException(status_code=400, detail="A correction note is required")
    conn = connect()
    try:
        finding = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        if finding is None:
            raise HTTPException(status_code=404, detail="Finding not found")
        member_engagement(conn, finding["engagement_id"], user, admin_may_read_metadata=False)
        reviewed_at = utc_now()
        note = body.note.strip() if body.note else None
        prior_status = finding["review_status"]
        conn.execute(
            """
            UPDATE findings
            SET review_status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (status_by_action[action], note, user.email, reviewed_at, finding_id),
        )
        append_event(
            conn,
            actor=user.email,
            action=event_by_action[action],
            object_type="finding",
            object_id=finding_id,
            payload={
                "review_status": status_by_action[action],
                "prior_review_status": prior_status,
                "rule_id": finding["rule_id"],
                "title": finding["title"],
                "engagement_id": finding["engagement_id"],
                "note": note,
                "has_note": bool(note),
            },
        )
        return next(item for item in findings_payload(conn, finding["engagement_id"]) if item["id"] == finding_id)
    finally:
        conn.close()


@app.get("/engagements/{engagement_id}/export")
def export_findings(engagement_id: str, user: CurrentUser = Depends(require("finding:export"))):
    conn = connect()
    try:
        engagement = member_engagement(conn, engagement_id, user, admin_may_read_metadata=False)
        payload = {
            "engagement": engagement_dict(engagement, conn),
            "findings": findings_payload(conn, engagement_id),
        }
        append_event(
            conn,
            actor=user.email,
            action="EXPORT_CREATED",
            object_type="engagement",
            object_id=engagement_id,
            payload={"format": "json", "finding_count": len(payload["findings"])},
        )
        body = json.dumps(payload, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{engagement_id}-findings.json"'},
        )
    finally:
        conn.close()


@app.get("/audit-events")
def audit_events(user: CurrentUser = Depends(require("audit:read"))):
    conn = connect()
    try:
        return [
            {
                "id": row["id"],
                "ts_utc": row["ts_utc"],
                "actor": row["actor"],
                "action": row["action"],
                "object_type": row["object_type"],
                "object_id": row["object_id"],
                "payload": event_payload(row),
                "payload_hash": row["payload_hash"],
                "prev_hash": row["prev_hash"],
                "chain_hash": row["chain_hash"],
            }
            for row in list_events(conn, newest_first=True)
        ]
    finally:
        conn.close()


@app.get("/users")
def list_users(user: CurrentUser = Depends(require("user:manage"))):
    del user
    conn = connect()
    try:
        rows = conn.execute("SELECT id, email, name, role, active FROM users ORDER BY email").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.post("/users")
def create_user(body: UserIn, user: CurrentUser = Depends(require("user:manage"))):
    email = body.email.strip().lower()
    if body.role not in rbac.PERMISSIONS:
        raise HTTPException(status_code=400, detail="Unknown role")
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="User already exists")
        user_id = new_id()
        conn.execute(
            "INSERT INTO users (id, email, name, role, password_hash, active) VALUES (?,?,?,?,?,1)",
            (user_id, email, body.name.strip(), body.role, rbac.hash_password(body.password)),
        )
        append_event(
            conn,
            actor=user.email,
            action="USER_CREATED",
            object_type="user",
            object_id=user_id,
            payload={"email": email, "role": body.role},
        )
        return {"id": user_id, "email": email, "name": body.name.strip(), "role": body.role, "active": 1}
    finally:
        conn.close()


@app.patch("/users/{user_id}")
def update_user(user_id: str, body: UserPatch, user: CurrentUser = Depends(require("user:manage"))):
    if body.role is not None and body.role not in rbac.PERMISSIONS:
        raise HTTPException(status_code=400, detail="Unknown role")
    if body.active is False and user_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    conn = connect()
    try:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="User not found")
        name = body.name.strip() if body.name else existing["name"]
        role = body.role or existing["role"]
        active = int(existing["active"] if body.active is None else body.active)
        conn.execute(
            "UPDATE users SET name = ?, role = ?, active = ? WHERE id = ?",
            (name, role, active, user_id),
        )
        append_event(
            conn,
            actor=user.email,
            action="USER_UPDATED",
            object_type="user",
            object_id=user_id,
            payload={"role": role, "active": active},
        )
        return {"id": user_id, "email": existing["email"], "name": name, "role": role, "active": active}
    finally:
        conn.close()


@app.get("/settings/retention")
def get_retention(user: CurrentUser = Depends(require("settings:manage"))):
    del user
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'retention'").fetchone()
        return json.loads(row["value"])
    finally:
        conn.close()


@app.put("/settings/retention")
def put_retention(body: RetentionIn, user: CurrentUser = Depends(require("settings:manage"))):
    conn = connect()
    try:
        value = {"retention_days": body.retention_days, "legal_hold": body.legal_hold}
        conn.execute("UPDATE settings SET value = ? WHERE key = 'retention'", (json.dumps(value),))
        append_event(
            conn,
            actor=user.email,
            action="SETTINGS_UPDATED",
            object_type="settings",
            object_id="retention",
            payload=value,
        )
        return value
    finally:
        conn.close()
