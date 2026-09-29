---
name: audit-security-perimeter
description: >-
  Enforces the audit_ai company perimeter: no public LLM or OCR, RBAC on every
  route, and an append-only audit log. Use when editing audit_ai auth, storage,
  model calls, logging, uploads, or any code that reads documents.
---

# Audit security perimeter

Read `audit_ai/SECURITY.md`. Apply it to every change under `audit_ai/`.

## Model and network

- Default `AUDIT_MODEL_MODE=heuristic`.
- `build_provider()` must reject hosts other than `localhost`, `127.0.0.1`, and `*.azure.com`.
- Do not add a public SDK client, LangChain, LangSmith, or a Hugging Face Inference call.
- Local and Azure providers may explain a finding. They receive finding JSON, not a file-reading tool.
- Classification and money extraction stay deterministic when the private model is absent.

## RBAC

Use the existing permission map in `audit_ai/backend/app/rbac.py`. New routes call it. File downloads also require engagement membership for every role.

## Audit log

Use `append_event` only. Do not add update or delete helpers. Do not drop the SQLite triggers on `audit_events`. New sensitive actions get a new event name and a metadata payload.

## Storage

Runtime files go under the configured data directory (gitignored). Sample PDFs under `audit_ai/samples/` stay synthetic. Do not point this app at Fabric Gold.
