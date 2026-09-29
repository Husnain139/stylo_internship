# Audit Document Reviewer

Prototype for a company procurement audit. Documents stay on this machine. The default model is a local heuristic: it does not call a public API.

Important data (extracted fields and PDF) and processed analysis (rules and arithmetic) are separate screens. A senior auditor confirms scope and approves findings. The audit log cannot be updated or deleted.

Read [SECURITY.md](SECURITY.md) before using real documents.

## Run the API

```bash
cd audit_ai/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_samples.py
python -m uvicorn app.main:app --port 8000
```

## Run the UI

```bash
cd audit_ai/web
npm install
npm run dev
```

Open http://localhost:3000.

Prototype accounts (password `prototype-only`, override with `AUDIT_BOOTSTRAP_PASSWORD`):

| Email | Role |
|---|---|
| junior.auditor@stylo.local | Junior Auditor |
| senior.auditor@stylo.local | Senior Auditor |
| admin.auditor@stylo.local | Administrator |

## Sample packs

Synthetic (and one open-source noise) PDFs live in `audit_ai/samples/`. Regenerate:

```bash
cd audit_ai/backend
python scripts/generate_samples.py
```

In the UI, pick a pack then **Load pack**. Packs cover mismatch, clean match, missing PO, duplicate payment, multi-vendor, kitchen-sink (all findings), incomplete evidence, scanned/OCR image-only PDFs, hybrid text+scan, and unknown/noise docs. PNG scans live under `samples/images/` for OCR experiments (uploader is PDF-only today). Do not commit real business documents.

## Tests

```bash
cd audit_ai/backend
python -m pytest
```

## What stays out of this prototype

Public LLM and OCR APIs, LangChain tracing, and the Fabric Gold lakehouse. A later deployment can switch `AUDIT_MODEL_MODE` to `local` (127.0.0.1 only) or `azure` (`*.azure.com` only).
