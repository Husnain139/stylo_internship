"""Ingest, scope, and analysis orchestration. Routes stay in main.py."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

from fastapi import HTTPException

from .audit_log import append_event
from .config import files_dir, samples_dir
from .pdf_text import read_pages
from .pipeline import analyze_documents, propose_scope
from .provider import PerimeterError, build_provider

SAMPLE_NAMES = (
    "purchase_order.pdf",
    "invoice.pdf",
    "payment.pdf",
    "approval_policy.pdf",
)

DEFAULT_SAMPLE_PACK = "mismatch"


def list_sample_packs() -> list[dict]:
    catalog = samples_dir() / "catalog.json"
    if catalog.is_file():
        try:
            return json.loads(catalog.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    packs = []
    root = samples_dir()
    if not root.is_dir():
        return packs
    for folder in sorted(root.iterdir()):
        meta = folder / "pack.json"
        if folder.is_dir() and meta.is_file():
            try:
                packs.append(json.loads(meta.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return packs


def resolve_sample_pack(pack_id: str | None) -> tuple[str, Path]:
    chosen = (pack_id or DEFAULT_SAMPLE_PACK).strip() or DEFAULT_SAMPLE_PACK
    folder = samples_dir() / chosen
    if folder.is_dir() and any(folder.glob("*.pdf")):
        return chosen, folder
    if chosen == DEFAULT_SAMPLE_PACK and (samples_dir() / "purchase_order.pdf").is_file():
        return chosen, samples_dir()
    raise HTTPException(status_code=404, detail=f"Sample pack not found: {chosen}")


def pack_pdf_names(folder: Path) -> list[str]:
    names = sorted(path.name for path in folder.glob("*.pdf"))
    if not names and folder == samples_dir():
        return list(SAMPLE_NAMES)
    return names


def new_id() -> str:
    return str(uuid.uuid4())


def analysis_run_count(conn: sqlite3.Connection, engagement_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM analysis_runs WHERE engagement_id = ?",
            (engagement_id,),
        ).fetchone()["n"]
    )


def engagement_dict(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict:
    count = analysis_run_count(conn, row["id"]) if conn is not None else 0
    return {
        "id": row["id"],
        "name": row["name"],
        "proposed_type": row["proposed_type"],
        "proposed_confidence": row["proposed_confidence"],
        "proposed_reasons": json.loads(row["proposed_reasons"]),
        "missing_evidence": json.loads(row["missing_evidence"]),
        "scope_status": row["scope_status"],
        "scope_audit_type": row["scope_audit_type"],
        "scope_confirmed_by": row["scope_confirmed_by"],
        "scope_confirmed_at": row["scope_confirmed_at"],
        "scope_rejected_by": row["scope_rejected_by"],
        "scope_rejected_at": row["scope_rejected_at"],
        "scope_rejection_note": row["scope_rejection_note"],
        "analysis_run_count": count,
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def document_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "engagement_id": row["engagement_id"],
        "filename": row["filename"],
        "sha256": row["sha256"],
        "page_count": row["page_count"],
        "document_class": row["document_class"],
        "class_confidence": row["class_confidence"],
        "class_reasons": json.loads(row["class_reasons"]),
        "uploaded_by": row["uploaded_by"],
        "uploaded_at": row["uploaded_at"],
    }


def field_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "field_name": row["field_name"],
        "value": row["value"],
        "page": row["page"],
        "confidence": row["confidence"],
        "validation_status": row["validation_status"],
        "source": row["source"],
    }


def recompute_scope(conn: sqlite3.Connection, engagement_id: str) -> None:
    classes = [
        row["document_class"]
        for row in conn.execute(
            "SELECT document_class FROM documents WHERE engagement_id = ?",
            (engagement_id,),
        ).fetchall()
    ]
    proposal = propose_scope(classes)
    conn.execute(
        """
        UPDATE engagements
        SET proposed_type = ?, proposed_confidence = ?, proposed_reasons = ?, missing_evidence = ?
        WHERE id = ?
        """,
        (
            proposal["proposed_type"],
            proposal["proposed_confidence"],
            json.dumps(proposal["proposed_reasons"]),
            json.dumps(proposal["missing_evidence"]),
            engagement_id,
        ),
    )


def ingest_bytes(
    conn: sqlite3.Connection,
    *,
    engagement_id: str,
    filename: str,
    payload: bytes,
    actor: str,
) -> dict:
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted in this prototype")
    if not payload:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(payload) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF exceeds the 20 MB prototype limit")

    digest = hashlib.sha256(payload).hexdigest()
    existing = conn.execute(
        "SELECT * FROM documents WHERE engagement_id = ? AND sha256 = ? ORDER BY uploaded_at LIMIT 1",
        (engagement_id, digest),
    ).fetchone()
    if existing is not None:
        append_event(
            conn,
            actor=actor,
            action="DOCUMENT_DUPLICATE_SKIPPED",
            object_type="document",
            object_id=existing["id"],
            payload={"filename": safe_name, "sha256": digest},
        )
        return document_dict(existing)

    document_id = new_id()
    stored_name = f"{document_id}.pdf"
    destination = files_dir() / stored_name
    destination.write_bytes(payload)
    try:
        pages = read_pages(destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The file is not a readable PDF") from exc

    text = "\n".join(page_text for _, page_text in pages)
    try:
        provider = build_provider()
    except PerimeterError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    classified = provider.complete(task="classify", data={"text": text})
    extracted = provider.complete(
        task="extract",
        data={"document_class": classified["document_class"], "pages": pages},
    )
    from .audit_log import utc_now

    uploaded_at = utc_now()
    conn.execute(
        """
        INSERT INTO documents (
          id, engagement_id, filename, sha256, page_count, stored_name, document_class,
          class_confidence, class_reasons, uploaded_by, uploaded_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            document_id,
            engagement_id,
            safe_name,
            digest,
            len(pages),
            stored_name,
            classified["document_class"],
            classified["confidence"],
            json.dumps(classified["reasons"]),
            actor,
            uploaded_at,
        ),
    )
    field_rows = []
    for field in extracted["fields"]:
        field_id = new_id()
        conn.execute(
            """
            INSERT INTO evidence_fields (
              id, document_id, field_name, value, page, confidence, validation_status, source
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                field_id,
                document_id,
                field["field_name"],
                field["value"],
                field["page"],
                field["confidence"],
                field["validation_status"],
                field["source"],
            ),
        )
        field_rows.append({"id": field_id, **field, "document_id": document_id})
    recompute_scope(conn, engagement_id)
    append_event(
        conn,
        actor=actor,
        action="DOCUMENT_INGESTED",
        object_type="document",
        object_id=document_id,
        payload={"filename": safe_name, "sha256": digest, "page_count": len(pages)},
    )
    append_event(
        conn,
        actor=actor,
        action="DOCUMENT_CLASSIFIED",
        object_type="document",
        object_id=document_id,
        payload={"document_class": classified["document_class"], "confidence": classified["confidence"]},
    )
    append_event(
        conn,
        actor=actor,
        action="EXTRACTION_COMPLETED",
        object_type="document",
        object_id=document_id,
        payload={"field_count": len(field_rows), "document_class": classified["document_class"]},
    )
    append_event(
        conn,
        actor=actor,
        action="MODEL_CALL",
        object_type="document",
        object_id=document_id,
        payload={"provider": provider.name, "task": "extract", "network": False},
    )
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    return document_dict(row)


def stored_file(stored_name: str) -> Path:
    root = files_dir().resolve()
    path = (root / Path(stored_name).name).resolve()
    if path.parent != root:
        raise HTTPException(status_code=400, detail="Stored file path is not valid")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file is missing")
    return path


def load_documents(conn: sqlite3.Connection, engagement_id: str) -> list[dict]:
    documents = []
    for row in conn.execute(
        "SELECT * FROM documents WHERE engagement_id = ? ORDER BY uploaded_at",
        (engagement_id,),
    ).fetchall():
        fields = [
            field_dict(field)
            for field in conn.execute(
                "SELECT * FROM evidence_fields WHERE document_id = ? ORDER BY field_name",
                (row["id"],),
            ).fetchall()
        ]
        item = document_dict(row)
        item["fields"] = fields
        documents.append(item)
    return distinct_by_hash(documents)


def distinct_by_hash(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    distinct = []
    for item in items:
        digest = item["sha256"]
        if digest in seen:
            continue
        seen.add(digest)
        distinct.append(item)
    return distinct


def run_analysis(conn: sqlite3.Connection, engagement_id: str, actor: str) -> dict:
    engagement = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,)).fetchone()
    if engagement["scope_status"] == "rejected":
        raise HTTPException(
            status_code=409,
            detail="A senior auditor rejected this scope. Confirm it before analysis",
        )
    if engagement["scope_status"] != "confirmed":
        raise HTTPException(status_code=409, detail="Confirm the audit scope before analysis")
    documents = load_documents(conn, engagement_id)
    if not documents:
        raise HTTPException(status_code=400, detail="Upload documents before analysis")
    append_event(
        conn,
        actor=actor,
        action="ANALYSIS_STARTED",
        object_type="engagement",
        object_id=engagement_id,
        payload={"document_count": len(documents)},
    )
    try:
        provider = build_provider()
    except PerimeterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    drafts = analyze_documents(documents)
    from .audit_log import utc_now

    run_id = new_id()
    created_at = utc_now()
    conn.execute(
        "INSERT INTO analysis_runs (id, engagement_id, created_at, created_by) VALUES (?,?,?,?)",
        (run_id, engagement_id, created_at, actor),
    )
    for draft in drafts:
        public = {
            "rule_id": draft["rule_id"],
            "title": draft["title"],
            "narrative_status": draft["narrative_status"],
            "delta_amount": draft["delta_amount"],
            "currency": draft["currency"],
            "risk_band": draft["risk_band"],
            "detail": draft["detail"],
        }
        explained = provider.complete(
            task="explain_finding",
            data={"finding": public, "draft_explanation": draft["explanation"]},
        )
        finding_id = new_id()
        conn.execute(
            """
            INSERT INTO findings (
              id, engagement_id, analysis_run_id, rule_id, title, narrative_status, delta_amount,
              currency, risk_band, explanation, evidence_ids, detail, review_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'open')
            """,
            (
                finding_id,
                engagement_id,
                run_id,
                draft["rule_id"],
                draft["title"],
                draft["narrative_status"],
                draft["delta_amount"],
                draft["currency"],
                draft["risk_band"],
                explained["explanation"],
                json.dumps(draft["evidence_ids"]),
                json.dumps(draft["detail"]),
            ),
        )
        append_event(
            conn,
            actor=actor,
            action="MODEL_CALL",
            object_type="finding",
            object_id=finding_id,
            payload={
                "provider": provider.name,
                "task": "explain_finding",
                "network": bool(provider.uses_network),
                "rule_id": draft["rule_id"],
            },
        )
    append_event(
        conn,
        actor=actor,
        action="ANALYSIS_COMPLETED",
        object_type="engagement",
        object_id=engagement_id,
        payload={"analysis_run_id": run_id, "finding_count": len(drafts)},
    )
    return {
        "analysis_run_id": run_id,
        "analysis_run_count": analysis_run_count(conn, engagement_id),
        "findings": findings_payload(conn, engagement_id),
    }


def findings_payload(conn: sqlite3.Connection, engagement_id: str) -> list[dict]:
    run = conn.execute(
        "SELECT id FROM analysis_runs WHERE engagement_id = ? ORDER BY created_at DESC LIMIT 1",
        (engagement_id,),
    ).fetchone()
    if run is None:
        return []
    findings = conn.execute(
        "SELECT * FROM findings WHERE analysis_run_id = ? ORDER BY rule_id",
        (run["id"],),
    ).fetchall()
    payloads = []
    for finding in findings:
        evidence_ids = json.loads(finding["evidence_ids"])
        evidence = []
        if evidence_ids:
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = conn.execute(
                f"""
                SELECT evidence_fields.*, documents.filename
                FROM evidence_fields
                JOIN documents ON documents.id = evidence_fields.document_id
                WHERE evidence_fields.id IN ({placeholders})
                """,
                evidence_ids,
            ).fetchall()
            evidence = [
                {
                    "id": row["id"],
                    "document_id": row["document_id"],
                    "filename": row["filename"],
                    "field_name": row["field_name"],
                    "value": row["value"],
                    "page": row["page"],
                    "validation_status": row["validation_status"],
                }
                for row in rows
            ]
        payloads.append(
            {
                "id": finding["id"],
                "engagement_id": finding["engagement_id"],
                "analysis_run_id": finding["analysis_run_id"],
                "rule_id": finding["rule_id"],
                "title": finding["title"],
                "narrative_status": finding["narrative_status"],
                "delta_amount": finding["delta_amount"],
                "currency": finding["currency"],
                "risk_band": finding["risk_band"],
                "explanation": finding["explanation"],
                "review_status": finding["review_status"],
                "review_note": finding["review_note"],
                "reviewed_by": finding["reviewed_by"],
                "reviewed_at": finding["reviewed_at"],
                "detail": json.loads(finding["detail"]),
                "evidence": evidence,
            }
        )
    return payloads


def load_sample_bytes(name: str, *, pack: str | None = None) -> bytes:
    if pack:
        _, folder = resolve_sample_pack(pack)
        path = folder / Path(name).name
    else:
        path = samples_dir() / Path(name).name
    if not path.is_file():
        raise HTTPException(status_code=500, detail=f"Synthetic sample is missing: {name}")
    return path.read_bytes()


def load_pack_documents(conn: sqlite3.Connection, engagement_id: str, actor: str, pack_id: str | None) -> list[dict]:
    chosen, folder = resolve_sample_pack(pack_id)
    loaded = []
    for name in pack_pdf_names(folder):
        loaded.append(
            ingest_bytes(
                conn,
                engagement_id=engagement_id,
                filename=name,
                payload=load_sample_bytes(name, pack=chosen),
                actor=actor,
            )
        )
    return loaded
