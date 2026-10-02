# Intelligent Document Processing (STL-AI-0014)

Controlled AI layer for Finance & Accounts:

1. **Upload** — Excel, CSV, PDF, Word, scanned images  
2. **AI Analysis** — `gpt-4o-mini` structure hints (hard token caps; sample / page only)  
3. **Clean & Standardize** — DuckDB blank-row drop, key dedupe, ERP column names  
4. **Validate** — DuckDB rule checks that create exceptions (capped for review)  
5. **Approve Exceptions** — mandatory human review  
6. **Export** — ERP-ready CSV always; XLSX when under the desk row limit  

## Setup

### Backend

```bash
cd IDP/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Ensure `IDP/.env` contains:

```env
OPENAI_API_KEY=sk-...
IDP_OPENAI_MODEL=gpt-4o-mini
IDP_OPENAI_MAX_OUTPUT_TOKENS=512
IDP_OPENAI_MAX_INPUT_CHARS=4000
IDP_OPENAI_MAX_SAMPLE_ROWS=15
IDP_OPENAI_TEMPERATURE=0
IDP_DUCKDB_MEMORY_GB=8
IDP_DUCKDB_THREADS=4
IDP_XLSX_MAX_ROWS=200000
```

### Frontend

```bash
cd IDP/web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API defaults to `http://127.0.0.1:8000`.

## Token discipline

| Setting | Default | Purpose |
|---|---|---|
| `IDP_OPENAI_MODEL` | `gpt-4o-mini` | Cost-efficient multimodal model |
| `IDP_OPENAI_MAX_INPUT_CHARS` | `4000` | Truncates tabular samples before the API call |
| `IDP_OPENAI_MAX_OUTPUT_TOKENS` | `512` | Caps completion size |
| `IDP_OPENAI_MAX_SAMPLE_ROWS` | `15` | Limits rows sent for structure analysis |
| `IDP_OPENAI_TEMPERATURE` | `0` | Deterministic schema suggestions |

DuckDB owns clean, validate, and large CSV export. OpenAI is used only for short structure analysis (and low-detail vision on scans). AI review checklist is advisory only.

## Large files (DuckDB)

CSV/Excel uploads are **streamed to disk**, then cleaned/validated with **DuckDB** (not a full Python in-memory ledger). Default soft upload cap is **10 GiB**. PDF/Word/images stay under `IDP_MAX_NON_TABULAR_BYTES` (default 100 MB): extract/spill to CSV, then the same DuckDB path. Scanned PDFs/images may use capped vision for structure recovery.

**Export:** cleaned **CSV always**. **XLSX only when** cleaned `row_count ≤ IDP_XLSX_MAX_ROWS` (default **200,000**). Prefer CSV for multi‑GB ERP extracts.

| Setting | Default | Purpose |
|---|---|---|
| `IDP_MAX_UPLOAD_BYTES` | `10737418240` (10 GiB) | Soft upload cap; `0` = no soft cap |
| `IDP_MAX_NON_TABULAR_BYTES` | `104857600` (100 MB) | PDF/Word/image guard |
| `IDP_SAMPLE_ROWS` | `8` | Rows kept for UI + AI samples |
| `IDP_DUCKDB_MEMORY_GB` | auto | DuckDB memory; omit to calculate from PC RAM |
| `IDP_DUCKDB_THREADS` | auto | DuckDB threads; omit to use ~half of CPU cores (2–8) |
| `IDP_XLSX_MAX_ROWS` | `200000` | Skip XLSX above this row count |
| `IDP_TEMP_DIR` | `data/tmp` | DuckDB spill directory |

### Auto memory formula

Detected total RAM → DuckDB budget:

1. Reserve `max(4 GiB, 25% of RAM)` for OS + Next.js + FastAPI  
2. DuckDB gets `min(remaining, 50% of RAM)`  
3. Clamp to **1–48 GiB**  
4. Threads = `clamp(CPU_count / 2, 2, 8)`

Examples:

| PC RAM | Reserve | DuckDB memory |
|---|---|---|
| 8 GB | 4 GB | ~3–4 GB |
| 16 GB | 4 GB | ~7.5–8 GB |
| 32 GB | 8 GB | ~16 GB |

`GET /health` returns the live sizing report (`duckdb` field). Set `IDP_DUCKDB_MEMORY_GB` / `IDP_DUCKDB_THREADS` to override.

SQLite stores metadata and samples only.

## Audit trail

Every upload, stage completion, exception decision, and export is appended to `audit_events` (SQLite, append-only triggers).

## Project layout

```
IDP/
  .env                 # secrets (gitignored)
  backend/app/         # FastAPI + DuckDB pipeline
  web/                 # Next.js desk UI
  data/                # runtime uploads/exports/db/tmp (gitignored)
```
