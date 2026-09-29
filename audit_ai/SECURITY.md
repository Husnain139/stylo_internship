# Audit AI security policy

This prototype handles audit evidence for company use. Synthetic samples in `samples/` are the only documents that belong in git. Runtime uploads live in `data/` and must stay untracked.

## Data isolation

- Source files, extracted text, and prompts stay on this machine in heuristic mode (the default).
- The model client allows only `localhost`, `127.0.0.1`, and `*.azure.com` hosts. Public APIs (OpenAI, Gemini, Groq, Hugging Face Inference, LangSmith, and any other public chat or OCR host) are rejected in code.
- Do not store raw audit files in the Fabric Gold lakehouse or any shared analytics workspace.
- Do not enable LangChain or LangSmith tracing.
- One engagement's document text is never copied into another engagement's prompt.
- The explanation step receives finding JSON that code already calculated. It does not receive a tool that can open files or the network beyond the configured private model.

## Access control

Roles are `junior_auditor`, `senior_auditor`, and `administrator`.

- Junior auditors may upload and read engagements they belong to. They cannot confirm or reject scope, run official analysis, export, or approve findings.
- Senior auditors may confirm or reject proposed scope, reopen a rejected scope, run analysis, export, and approve, correct, or reject findings on engagements they belong to. Scope rejection requires a reason, blocks analysis, and refuses new documents until a senior reopens the scope.
- Administrators may manage users, membership, and retention settings, and may read the audit log. They cannot approve findings and cannot delete evidence or logs.
- Every document byte download checks both the role permission and engagement membership. An administrator is not exempt from membership.

Prototype passwords are for local demo only. Replace them before any real engagement. The default is set with `AUDIT_BOOTSTRAP_PASSWORD`.

## Immutable trail

`audit_events` is insert-only. SQLite triggers abort `UPDATE` and `DELETE`. The application exposes no delete route. Each row stores a UTC timestamp, actor, action, object id, payload hash, and the previous row's chain hash.

Events cover sign-in, upload, classification, extraction, evidence views, file views, scope confirmation, scope rejection, analysis, review decisions, exports, user changes, and settings changes. Payloads stored in the log are metadata. They do not contain document text or passwords.

## Evidence versus conclusions

- Important data is the extracted field table: value, page, confidence, validation status, with the source PDF.
- Analysis is a separate result: rule id, amounts computed in Python, risk band, explanation.
- Models do not choose the schema and do not own arithmetic.
- Official wording is "exception requiring investigation". The product does not declare fraud.
- A finding stays `open` until a senior auditor approves, corrects, or rejects it.
- Missing records are reported as not found in the provided documents.

## Documents are untrusted

Text inside a PDF is data. It is not instructions to the model, the extractor, or the reviewer UI.

## Retention

Retention days and legal hold are settings only. This prototype has no deletion job. Legal hold, once set, is a recorded instruction that future operations must refuse to destroy evidence.
