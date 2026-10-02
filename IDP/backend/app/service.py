"""Job orchestration for the six-stage IDP pipeline (disk-backed for large files)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .config import exports_dir, max_upload_bytes, uploads_dir
from .db import append_event, db, dumps, init_db, loads, row_to_dict, touch_job
from .export import export_erp_files, export_from_clean_csv
from .extractors import SUPPORTED_EXTENSIONS
from .openai_client import (
    OpenAIConfigError,
    analyze_structure,
    materialize_vision_table,
    plan_remediations_from_notes,
    review_checklist,
)
from .remediate import apply_remediations_to_csv, read_csv_sample
from .stream import fetch_clean_row, materialize_upload, stream_clean, stream_validate, table_paths, write_dicts_csv

STAGES = ("upload", "analyze", "clean", "validate", "approve", "export")
CHUNK = 1024 * 1024


def bootstrap() -> None:
    init_db()
    uploads_dir().mkdir(parents=True, exist_ok=True)
    exports_dir().mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_job_from_upload(
    *,
    filename: str,
    content_type: str | None,
    data: bytes | None = None,
    stream: BinaryIO | None = None,
    actor: str = "finance_user",
) -> dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    job_id = str(uuid.uuid4())
    dest = uploads_dir() / f"{job_id}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    limit = max_upload_bytes()

    if stream is not None:
        with dest.open("wb") as out:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if limit and total > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise ValueError(f"File exceeds the {limit // (1024 * 1024)} MB upload limit.")
                digest.update(chunk)
                out.write(chunk)
    else:
        payload = data or b""
        total = len(payload)
        if not payload:
            raise ValueError("Empty file upload.")
        if limit and total > limit:
            raise ValueError(f"File exceeds the {limit // (1024 * 1024)} MB upload limit.")
        digest.update(payload)
        dest.write_bytes(payload)

    if total <= 0:
        dest.unlink(missing_ok=True)
        raise ValueError("Empty file upload.")

    sha = digest.hexdigest()
    now = _utc_now()

    with db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, filename, content_type, file_path, sha256, status, stage,
                source_kind, raw_preview, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                filename,
                content_type,
                str(dest),
                sha,
                "uploaded",
                "upload",
                None,
                None,
                now,
                now,
            ),
        )
        append_event(
            conn,
            event="file_uploaded",
            actor=actor,
            job_id=job_id,
            metadata={"filename": filename, "sha256": sha, "bytes": total},
        )

    return run_through_analyze(job_id, actor=actor)


def run_through_analyze(job_id: str, *, actor: str = "system") -> dict[str, Any]:
    """Upload → materialize → AI analyze, then pause for human clean choices."""
    job = get_job(job_id)
    if not job:
        raise KeyError("Job not found")

    path = Path(job["file_path"])
    try:
        extracted = materialize_upload(path, filename=job["filename"], job_id=job_id)
    except Exception as exc:  # noqa: BLE001
        with db() as conn:
            touch_job(conn, job_id, status="failed", error=str(exc)[:500])
            append_event(conn, event="pipeline_failed", actor=actor, job_id=job_id, metadata={"error": str(exc)[:300]})
        raise ValueError(f"Could not process file: {exc}") from exc

    preview = {
        "kind": extracted.get("kind"),
        "sheet_name": extracted.get("sheet_name"),
        "columns": extracted.get("columns"),
        "row_count": extracted.get("row_count"),
        "sample_rows": (extracted.get("sample_rows") or [])[:8],
        "notes": extracted.get("notes"),
        "disk_backed": bool(extracted.get("disk_backed")),
        "raw_table": extracted.get("raw_table"),
        "needs_vision": bool(extracted.get("needs_vision")),
    }

    with db() as conn:
        touch_job(
            conn,
            job_id,
            stage="analyze",
            status="analyzing",
            source_kind=extracted.get("kind"),
            raw_preview=dumps(preview),
            error=None,
        )
        append_event(conn, event="stage_analyze_started", actor=actor, job_id=job_id)

    try:
        analysis = analyze_structure(
            {
                "kind": extracted.get("kind"),
                "sheet_name": extracted.get("sheet_name"),
                "columns": extracted.get("columns") or [],
                "row_count": extracted.get("row_count"),
                "sample_rows": extracted.get("sample_rows") or [],
                "notes": extracted.get("notes"),
                "needs_vision": bool(extracted.get("needs_vision")),
                "file_b64": extracted.get("file_b64"),
                "mime": extracted.get("mime"),
            }
        )
    except OpenAIConfigError as exc:
        with db() as conn:
            touch_job(conn, job_id, status="failed", error=str(exc)[:500])
            append_event(
                conn,
                event="pipeline_failed",
                actor=actor,
                job_id=job_id,
                metadata={"error": str(exc)[:300]},
            )
        raise ValueError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        if extracted.get("needs_vision"):
            with db() as conn:
                touch_job(conn, job_id, status="failed", error=str(exc)[:500])
                append_event(
                    conn,
                    event="pipeline_failed",
                    actor=actor,
                    job_id=job_id,
                    metadata={"error": str(exc)[:300]},
                )
            raise ValueError(f"OpenAI vision analysis failed: {exc}") from exc
        raise

    raw_path, _clean_path = table_paths(job_id)
    vision_rows = analysis.get("_vision_rows")
    vision_cols = analysis.get("_vision_columns")
    if isinstance(vision_rows, list) and vision_rows:
        cols = list(vision_cols) if isinstance(vision_cols, list) and vision_cols else list(vision_rows[0].keys())
        write_dicts_csv(raw_path, cols, vision_rows)
        analysis = {
            **analysis,
            "columns": analysis.get("columns")
            or [{"name": c, "erp_name": c, "dtype": "string"} for c in cols],
        }

    # Scans/images: OpenAI must produce a raw table before clean can start.
    if not raw_path.is_file() and extracted.get("needs_vision") and extracted.get("file_b64"):
        try:
            cols, rows, recovered = materialize_vision_table(
                {
                    "kind": extracted.get("kind"),
                    "notes": extracted.get("notes"),
                    "needs_vision": True,
                    "file_b64": extracted.get("file_b64"),
                    "mime": extracted.get("mime"),
                    "columns": extracted.get("columns") or [],
                    "sample_rows": [],
                }
            )
        except OpenAIConfigError as exc:
            with db() as conn:
                touch_job(conn, job_id, status="failed", error=str(exc)[:500])
                append_event(
                    conn,
                    event="pipeline_failed",
                    actor=actor,
                    job_id=job_id,
                    metadata={"error": str(exc)[:300]},
                )
            raise ValueError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            with db() as conn:
                touch_job(conn, job_id, status="failed", error=str(exc)[:500])
                append_event(
                    conn,
                    event="pipeline_failed",
                    actor=actor,
                    job_id=job_id,
                    metadata={"error": str(exc)[:300]},
                )
            raise ValueError(f"OpenAI vision recovery failed: {exc}") from exc

        write_dicts_csv(raw_path, cols, rows)
        analysis = {
            **recovered,
            "columns": recovered.get("columns")
            or [{"name": c, "erp_name": c, "dtype": "string"} for c in cols],
            "_meta": {
                **(recovered.get("_meta") or {}),
                **(analysis.get("_meta") or {}),
                "vision_materialized": True,
            },
        }

    if not raw_path.is_file():
        message = (
            "Raw table materialization missing. "
            "For scanned PDFs/images set OPENAI_API_KEY in IDP/.env, or upload CSV/Excel."
        )
        with db() as conn:
            touch_job(conn, job_id, status="failed", error=message[:500])
            append_event(
                conn,
                event="pipeline_failed",
                actor=actor,
                job_id=job_id,
                metadata={"error": message[:300]},
            )
        raise ValueError(message)

    with db() as conn:
        touch_job(
            conn,
            job_id,
            stage="clean",
            status="awaiting_clean",
            analysis_json=dumps({k: v for k, v in analysis.items() if not str(k).startswith("_vision")}),
        )
        append_event(
            conn,
            event="stage_analyze_completed",
            actor=actor,
            job_id=job_id,
            metadata=analysis.get("_meta") or {},
        )
        append_event(
            conn,
            event="stage_clean_awaiting",
            actor=actor,
            job_id=job_id,
            metadata={"message": "Human clean choices required"},
        )

    return get_job_detail(job_id)


def apply_clean(
    job_id: str,
    *,
    drop_blank_rows: bool = True,
    drop_blank_keys: bool = True,
    dedupe_keys: bool = True,
    drop_exact_duplicates: bool = False,
    rename_erp: bool = True,
    trim_whitespace: bool = True,
    nullify_placeholders: bool = True,
    normalize_numbers: bool = True,
    standardize_dates: bool = True,
    lowercase_emails: bool = True,
    uppercase_ids: bool = False,
    actor: str = "finance_user",
) -> dict[str, Any]:
    """Apply chosen clean steps, then validate. Auto uses recommended defaults."""
    job = get_job(job_id)
    if not job:
        raise KeyError("Job not found")
    if job.get("status") == "exported":
        raise PermissionError("Exported jobs cannot be re-cleaned.")

    analysis = loads(job.get("analysis_json"), {}) or {}
    raw_path, clean_path = table_paths(job_id)
    if not raw_path.is_file():
        raise ValueError("Raw table missing — re-upload the file.")

    clean_kwargs = {
        "drop_blank_rows": drop_blank_rows,
        "drop_blank_keys": drop_blank_keys,
        "dedupe_keys": dedupe_keys,
        "drop_exact_duplicates": drop_exact_duplicates,
        "rename_erp": rename_erp,
        "trim_whitespace": trim_whitespace,
        "nullify_placeholders": nullify_placeholders,
        "normalize_numbers": normalize_numbers,
        "standardize_dates": standardize_dates,
        "lowercase_emails": lowercase_emails,
        "uppercase_ids": uppercase_ids,
    }

    with db() as conn:
        touch_job(conn, job_id, stage="clean", status="cleaning", error=None)
        append_event(
            conn,
            event="stage_clean_started",
            actor=actor,
            job_id=job_id,
            metadata=clean_kwargs,
        )

    cleaned = stream_clean(
        raw_path=raw_path,
        clean_path=clean_path,
        analysis=analysis,
        **clean_kwargs,
    )
    cleaned_store = {
        **cleaned,
        "rows": cleaned.get("sample_rows") or [],
    }

    with db() as conn:
        touch_job(
            conn,
            job_id,
            stage="validate",
            status="validating",
            cleaned_json=dumps(cleaned_store),
            validation_json=None,
            export_path=None,
        )
        append_event(
            conn,
            event="stage_clean_completed",
            actor=actor,
            job_id=job_id,
            metadata={**(cleaned.get("stats") or {}), **(cleaned.get("options") or {})},
        )

    validation = stream_validate(clean_path, cleaned, analysis)
    checklist = review_checklist(
        columns=list(cleaned.get("columns") or []),
        sample_rows=list(cleaned.get("sample_rows") or []),
        key_columns=list(cleaned.get("key_columns") or analysis.get("key_columns") or []),
        exception_codes=[str(e.get("code") or "") for e in (validation.get("exceptions") or [])],
        row_count=int(cleaned.get("row_count") or 0),
        document_type=str(analysis.get("document_type") or "") or None,
        dtypes=dict(cleaned.get("dtypes") or {}),
    )

    with db() as conn:
        conn.execute("DELETE FROM exceptions WHERE job_id = ?", (job_id,))
        for exc in validation.get("exceptions") or []:
            conn.execute(
                """
                INSERT INTO exceptions (
                    id, job_id, code, severity, message, row_index, field_name,
                    value_json, explanation, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    exc["id"],
                    job_id,
                    exc["code"],
                    exc["severity"],
                    exc["message"],
                    exc.get("row_index"),
                    exc.get("field_name"),
                    dumps(exc.get("value")),
                    None,
                    "pending",
                ),
            )
        next_status = "awaiting_approval" if validation.get("exception_count") else "ready_to_export"
        touch_job(
            conn,
            job_id,
            stage="approve" if validation.get("exception_count") else "export",
            status=next_status,
            validation_json=dumps(
                {
                    "ok": validation.get("ok"),
                    "exception_count": validation.get("exception_count"),
                    "truncated": validation.get("truncated"),
                    "summary": validation.get("summary"),
                    "review_checklist": checklist,
                }
            ),
        )
        append_event(
            conn,
            event="stage_validate_completed",
            actor=actor,
            job_id=job_id,
            metadata={
                "exception_count": validation.get("exception_count"),
                "ok": validation.get("ok"),
                "checklist_provider": (checklist.get("_meta") or {}).get("provider"),
            },
        )

    if not validation.get("exception_count"):
        try:
            apply_post_approval_remediations(job_id, actor=actor)
        except Exception as exc:  # noqa: BLE001
            with db() as conn:
                append_event(
                    conn,
                    event="remediation_failed",
                    actor=actor,
                    job_id=job_id,
                    metadata={"error": str(exc)[:300]},
                )

    return get_job_detail(job_id)


def run_through_validate(job_id: str, *, actor: str = "system") -> dict[str, Any]:
    """Backward-compatible helper: analyze then auto-clean (all options on)."""
    run_through_analyze(job_id, actor=actor)
    return apply_clean(job_id, actor=actor)


def decide_exception(
    job_id: str,
    exception_id: str,
    *,
    decision: str,
    note: str | None = None,
    actor: str = "finance_user",
) -> dict[str, Any]:
    decision = decision.lower().strip()
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    with db() as conn:
        row = conn.execute(
            "SELECT * FROM exceptions WHERE id = ? AND job_id = ?",
            (exception_id, job_id),
        ).fetchone()
        if row is None:
            raise KeyError("Exception not found")
        status = "approved" if decision == "approve" else "rejected"
        conn.execute(
            """
            UPDATE exceptions
            SET status = ?, decision_note = ?, decided_at = datetime('now')
            WHERE id = ?
            """,
            (status, (note or "").strip() or None, exception_id),
        )
        append_event(
            conn,
            event="exception_decided",
            actor=actor,
            job_id=job_id,
            metadata={"exception_id": exception_id, "decision": status, "note": note},
        )

        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM exceptions WHERE job_id = ? AND status = 'pending'",
            (job_id,),
        ).fetchone()["c"]
        rejected = conn.execute(
            "SELECT COUNT(*) AS c FROM exceptions WHERE job_id = ? AND status = 'rejected'",
            (job_id,),
        ).fetchone()["c"]

        if pending == 0 and rejected == 0:
            touch_job(conn, job_id, stage="export", status="ready_to_export")
            append_event(conn, event="exceptions_cleared", actor=actor, job_id=job_id)
        elif pending == 0 and rejected > 0:
            touch_job(conn, job_id, stage="approve", status="blocked_rejections")
            append_event(
                conn,
                event="export_blocked",
                actor=actor,
                job_id=job_id,
                metadata={"rejected": rejected},
            )
        else:
            touch_job(conn, job_id, stage="approve", status="awaiting_approval")

    if pending == 0 and rejected == 0:
        try:
            apply_post_approval_remediations(job_id, actor=actor)
        except Exception as exc:  # noqa: BLE001 — still allow export of clean CSV
            with db() as conn:
                append_event(
                    conn,
                    event="remediation_failed",
                    actor=actor,
                    job_id=job_id,
                    metadata={"error": str(exc)[:300]},
                )

    return get_job_detail(job_id)


def apply_post_approval_remediations(job_id: str, *, actor: str = "finance_user") -> dict[str, Any]:
    """After all exceptions are approved, apply note/checklist steps and write result CSV."""
    detail = get_job_detail(job_id)
    if not detail:
        raise KeyError("Job not found")

    _, clean_path = table_paths(job_id)
    if not clean_path.is_file():
        raise ValueError("Clean table missing.")

    columns, sample_rows = read_csv_sample(clean_path, limit=12)
    cleaned = detail.get("cleaned") or {}
    if not columns:
        columns = list(cleaned.get("columns") or [])

    exception_notes = []
    for exc in detail.get("exceptions") or []:
        if exc.get("status") != "approved":
            continue
        note = (exc.get("decision_note") or "").strip()
        if not note:
            continue
        exception_notes.append(
            {
                "exception_id": exc.get("id"),
                "code": exc.get("code"),
                "message": exc.get("message"),
                "row_index": exc.get("row_index"),
                "field_name": exc.get("field_name"),
                "note": note,
            }
        )

    checklist = ((detail.get("validation") or {}).get("review_checklist") or {})
    checklist_steps = list(checklist.get("focus") or [])

    plan = plan_remediations_from_notes(
        columns=columns,
        exception_notes=exception_notes,
        checklist_steps=[str(s) for s in checklist_steps],
        sample_rows=sample_rows,
    )

    result_path = exports_dir() / f"{job_id}_result.csv"
    stats = apply_remediations_to_csv(
        clean_path,
        remediations=list(plan.get("remediations") or []),
        result_path=result_path,
    )

    # Keep clean.csv aligned with the post-approval result for export.
    if stats.get("changes_applied") or stats.get("rows_dropped"):
        import shutil

        shutil.copyfile(result_path, clean_path)
    else:
        import shutil

        shutil.copyfile(clean_path, result_path)
        stats["result_path"] = str(result_path)

    cleaned_store = {
        **cleaned,
        "row_count": stats.get("row_count", cleaned.get("row_count")),
        "result_path": str(result_path),
        "remediations": {
            "summary": plan.get("summary"),
            "steps_considered": checklist_steps,
            "notes_considered": exception_notes,
            "applied": stats.get("applied") or [],
            "changes_applied": stats.get("changes_applied"),
            "rows_dropped": stats.get("rows_dropped"),
            "_meta": plan.get("_meta"),
        },
    }
    # Keep a short preview for UI
    preview_cols, preview_rows = read_csv_sample(result_path, limit=8)
    cleaned_store["columns"] = preview_cols or columns
    cleaned_store["rows"] = preview_rows
    cleaned_store["sample_rows"] = preview_rows

    with db() as conn:
        touch_job(conn, job_id, cleaned_json=dumps(cleaned_store))
        append_event(
            conn,
            event="remediation_applied",
            actor=actor,
            job_id=job_id,
            metadata={
                "changes_applied": stats.get("changes_applied"),
                "rows_dropped": stats.get("rows_dropped"),
                "result_path": str(result_path),
                "summary": plan.get("summary"),
            },
        )
    return cleaned_store


def approve_all_pending(job_id: str, *, actor: str = "finance_user", note: str | None = None) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id FROM exceptions WHERE job_id = ? AND status = 'pending'",
            (job_id,),
        ).fetchall()
        ids = [r["id"] for r in rows]
    detail = get_job_detail(job_id)
    for exc_id in ids:
        detail = decide_exception(job_id, exc_id, decision="approve", note=note, actor=actor)
    return detail


def export_job(job_id: str, *, actor: str = "finance_user") -> dict[str, Any]:
    detail = get_job_detail(job_id)
    if not detail:
        raise KeyError("Job not found")

    pending = [e for e in detail.get("exceptions") or [] if e["status"] == "pending"]
    rejected = [e for e in detail.get("exceptions") or [] if e["status"] == "rejected"]
    if pending:
        raise PermissionError("Cannot export while exceptions are pending human review.")
    if rejected:
        raise PermissionError("Cannot export while rejected exceptions remain unresolved.")

    _, clean_path = table_paths(job_id)
    cleaned = detail.get("cleaned") or {}
    if clean_path.is_file():
        result = export_from_clean_csv(
            clean_path,
            columns=list(cleaned.get("columns") or []),
            export_dir=exports_dir(),
            job_id=job_id,
            basename=detail["filename"],
            row_count=int(cleaned.get("row_count") or 0) or None,
        )
    elif cleaned.get("rows"):
        result = export_erp_files(
            cleaned,
            export_dir=exports_dir(),
            job_id=job_id,
            basename=detail["filename"],
        )
    else:
        raise ValueError("No cleaned data available to export.")

    with db() as conn:
        touch_job(
            conn,
            job_id,
            stage="export",
            status="exported",
            export_path=result["csv_path"],
            cleaned_json=dumps(
                {
                    **cleaned,
                    "export_formats": result.get("formats") or ["csv"],
                    "xlsx_skipped_reason": result.get("xlsx_skipped_reason"),
                }
            ),
        )
        append_event(
            conn,
            event="stage_export_completed",
            actor=actor,
            job_id=job_id,
            metadata=result,
        )

    return get_job_detail(job_id)


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, content_type, status, stage, source_kind,
                   created_at, updated_at, sha256
            FROM jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(200, limit)),),
        ).fetchall()
    return [dict(r) for r in rows]


def get_job(job_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row_to_dict(row)


def get_job_detail(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise KeyError("Job not found")
    with db() as conn:
        exceptions = conn.execute(
            """
            SELECT id, code, severity, message, row_index, field_name, value_json,
                   explanation, status, decision_note, decided_at, created_at
            FROM exceptions
            WHERE job_id = ?
            ORDER BY
              CASE status WHEN 'pending' THEN 0 WHEN 'rejected' THEN 1 ELSE 2 END,
              CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              created_at
            """,
            (job_id,),
        ).fetchall()
        events = conn.execute(
            """
            SELECT id, event, actor, metadata_json, created_at
            FROM audit_events
            WHERE job_id = ?
            ORDER BY id ASC
            """,
            (job_id,),
        ).fetchall()

    exc_list = []
    for e in exceptions:
        item = dict(e)
        item["value"] = loads(item.pop("value_json"), None)
        exc_list.append(item)

    audit = []
    for ev in events:
        item = dict(ev)
        item["metadata"] = loads(item.pop("metadata_json"), {})
        audit.append(item)

    cleaned = loads(job.get("cleaned_json"), {}) or {}
    # Prefer sample_rows for UI; expose row_count from stats.
    if cleaned.get("sample_rows") and not cleaned.get("rows"):
        cleaned = {**cleaned, "rows": cleaned.get("sample_rows") or []}

    export_formats = list(cleaned.get("export_formats") or [])
    xlsx_skipped_reason = cleaned.get("xlsx_skipped_reason")
    if job.get("status") == "exported" and job.get("export_path"):
        csv_path = Path(job["export_path"])
        xlsx_path = csv_path.with_suffix(".xlsx")
        if not export_formats:
            export_formats = ["csv"]
            if xlsx_path.is_file():
                export_formats.append("xlsx")
        if "xlsx" not in export_formats and not xlsx_skipped_reason:
            xlsx_skipped_reason = "XLSX not available for this export — use CSV."

    return {
        "id": job["id"],
        "filename": job["filename"],
        "content_type": job["content_type"],
        "sha256": job["sha256"],
        "status": job["status"],
        "stage": job["stage"],
        "source_kind": job["source_kind"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "error": job["error"],
        "raw_preview": loads(job.get("raw_preview"), {}),
        "analysis": loads(job.get("analysis_json"), {}),
        "cleaned": cleaned,
        "validation": loads(job.get("validation_json"), {}),
        "export_path": job.get("export_path"),
        "export_formats": export_formats,
        "xlsx_skipped_reason": xlsx_skipped_reason,
        "exceptions": exc_list,
        "audit_trail": audit,
        "stages": list(STAGES),
    }


def get_exception_row(job_id: str, exception_id: str) -> dict[str, Any]:
    """Open a single faulty cleaned row for an exception (not the whole ledger)."""
    job = get_job(job_id)
    if not job:
        raise KeyError("Job not found")

    with db() as conn:
        row = conn.execute(
            """
            SELECT id, code, severity, message, row_index, field_name, value_json, status, decision_note
            FROM exceptions
            WHERE job_id = ? AND id = ?
            """,
            (job_id, exception_id),
        ).fetchone()
    if not row:
        raise KeyError("Exception not found")

    exc = dict(row)
    exc["value"] = loads(exc.pop("value_json"), None)
    row_index = exc.get("row_index")
    cleaned_meta = loads(job.get("cleaned_json"), {}) or {}
    columns = list(cleaned_meta.get("columns") or [])

    payload: dict[str, Any] = {
        "exception": {
            "id": exc["id"],
            "code": exc["code"],
            "severity": exc["severity"],
            "message": exc["message"],
            "row_index": row_index,
            "field_name": exc.get("field_name"),
            "value": exc.get("value"),
            "status": exc.get("status"),
            "decision_note": exc.get("decision_note"),
        },
        "columns": columns,
        "row": None,
        "row_count": cleaned_meta.get("row_count"),
        "available": False,
        "reason": None,
    }

    if row_index is None:
        payload["reason"] = "This exception is not tied to a specific cleaned row."
        return payload

    _, clean_path = table_paths(job_id)
    fetched = fetch_clean_row(clean_path, int(row_index))
    if not fetched:
        # Fall back to in-memory sample if disk row is unavailable.
        sample_rows = list(cleaned_meta.get("sample_rows") or cleaned_meta.get("rows") or [])
        if 0 <= int(row_index) < len(sample_rows):
            payload["row"] = sample_rows[int(row_index)]
            payload["columns"] = columns or list(sample_rows[int(row_index)].keys())
            payload["available"] = True
            payload["reason"] = "Showing cached sample row (clean table lookup missed)."
            return payload
        payload["reason"] = f"Cleaned row {row_index} was not found."
        return payload

    payload["row"] = fetched["row"]
    payload["columns"] = fetched["columns"] or columns
    payload["row_count"] = fetched.get("row_count")
    payload["available"] = True
    return payload


def get_export_path(job_id: str, fmt: str = "csv") -> Path:
    job = get_job(job_id)
    if not job:
        raise FileNotFoundError("Export not available")
    cleaned = loads(job.get("cleaned_json"), {}) or {}

    if fmt == "result":
        result = cleaned.get("result_path")
        path = Path(result) if result else exports_dir() / f"{job_id}_result.csv"
        if not path.is_file():
            raise FileNotFoundError("Result CSV not available yet — finish approval first.")
        return path

    if job.get("status") != "exported":
        raise FileNotFoundError("Export not available")
    csv_path = Path(job["export_path"]) if job.get("export_path") else None
    if not csv_path or not csv_path.is_file():
        raise FileNotFoundError("Export file missing")
    if fmt == "csv":
        return csv_path
    if fmt == "xlsx":
        xlsx = csv_path.with_suffix(".xlsx")
        if not xlsx.is_file():
            raise FileNotFoundError(
                "XLSX export missing (large files are CSV-only above the desk row limit)"
            )
        return xlsx
    raise ValueError("fmt must be csv, xlsx, or result")
