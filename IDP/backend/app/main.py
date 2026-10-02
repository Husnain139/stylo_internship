"""FastAPI entrypoint for Intelligent Document Processing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import cors_origins, duckdb_sizing_report, openai_model
from .service import (
    apply_clean,
    approve_all_pending,
    bootstrap,
    create_job_from_upload,
    decide_exception,
    export_job,
    get_exception_row,
    get_export_path,
    get_job_detail,
    list_jobs,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    bootstrap()
    yield


app = FastAPI(
    title="Intelligent Document Processing",
    description="Controlled AI layer: Upload → Analyze → Clean → Validate → Approve → Export",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DecisionBody(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=1000)


class ApproveAllBody(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class CleanBody(BaseModel):
    drop_blank_rows: bool = True
    drop_blank_keys: bool = True
    dedupe_keys: bool = True
    drop_exact_duplicates: bool = False
    rename_erp: bool = True
    trim_whitespace: bool = True
    nullify_placeholders: bool = True
    normalize_numbers: bool = True
    standardize_dates: bool = True
    lowercase_emails: bool = True
    uppercase_ids: bool = False
    mode: str = Field(default="custom", pattern="^(auto|custom)$")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "idp",
        "model": openai_model(),
        "duckdb": duckdb_sizing_report(),
    }


@app.get("/api/jobs")
def api_list_jobs(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    return {"jobs": list_jobs(limit)}


@app.post("/api/jobs/upload")
async def api_upload(
    file: UploadFile = File(...),
    x_actor: str = Header(default="finance_user", alias="X-Actor"),
) -> dict[str, Any]:
    try:
        return create_job_from_upload(
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            stream=file.file,
            actor=(x_actor or "finance_user")[:120],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str) -> dict[str, Any]:
    try:
        return get_job_detail(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.post("/api/jobs/{job_id}/clean")
def api_clean(
    job_id: str,
    body: CleanBody,
    x_actor: str = Header(default="finance_user", alias="X-Actor"),
) -> dict[str, Any]:
    try:
        if body.mode == "auto":
            return apply_clean(job_id, actor=(x_actor or "finance_user")[:120])
        return apply_clean(
            job_id,
            drop_blank_rows=body.drop_blank_rows,
            drop_blank_keys=body.drop_blank_keys,
            dedupe_keys=body.dedupe_keys,
            drop_exact_duplicates=body.drop_exact_duplicates,
            rename_erp=body.rename_erp,
            trim_whitespace=body.trim_whitespace,
            nullify_placeholders=body.nullify_placeholders,
            normalize_numbers=body.normalize_numbers,
            standardize_dates=body.standardize_dates,
            lowercase_emails=body.lowercase_emails,
            uppercase_ids=body.uppercase_ids,
            actor=(x_actor or "finance_user")[:120],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/exceptions/{exception_id}/row")
def api_exception_row(job_id: str, exception_id: str) -> dict[str, Any]:
    try:
        return get_exception_row(job_id, exception_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/exceptions/{exception_id}/decide")
def api_decide(
    job_id: str,
    exception_id: str,
    body: DecisionBody,
    x_actor: str = Header(default="finance_user", alias="X-Actor"),
) -> dict[str, Any]:
    try:
        return decide_exception(
            job_id,
            exception_id,
            decision=body.decision,
            note=body.note,
            actor=(x_actor or "finance_user")[:120],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/exceptions/approve-all")
def api_approve_all(
    job_id: str,
    body: ApproveAllBody,
    x_actor: str = Header(default="finance_user", alias="X-Actor"),
) -> dict[str, Any]:
    try:
        return approve_all_pending(
            job_id,
            actor=(x_actor or "finance_user")[:120],
            note=body.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.post("/api/jobs/{job_id}/export")
def api_export(
    job_id: str,
    x_actor: str = Header(default="finance_user", alias="X-Actor"),
) -> dict[str, Any]:
    try:
        return export_job(job_id, actor=(x_actor or "finance_user")[:120])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/download")
def api_download(job_id: str, fmt: str = Query("csv", pattern="^(csv|xlsx|result)$")) -> FileResponse:
    try:
        path = get_export_path(job_id, fmt=fmt)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if fmt == "xlsx":
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        media = "text/csv"
    return FileResponse(path, media_type=media, filename=path.name)
