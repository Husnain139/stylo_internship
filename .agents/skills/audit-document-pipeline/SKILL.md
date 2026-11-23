---
name: audit-document-pipeline
description: >-
  Implements the audit document pipeline for audit_ai: ingest, classify,
  schema extraction, raw evidence display, and separate code-based analysis.
  Use when editing audit_ai, adding document types, extraction fields,
  reconciliation rules, findings, or the reviewer UI.
---

# Audit document pipeline

Work in `audit_ai/`. Read `audit_ai/SECURITY.md` before changing the pipeline.

## Stage order

1. Ingest: store bytes, SHA-256, page count, `document_id`. The same SHA-256 in one engagement is not stored again.
2. Classify the document (`invoice`, `purchase_order`, `payment`, `policy`, or `unknown`) and update the proposed engagement scope.
3. Extract into the schema for that class. Validate in Python. This is raw evidence.
4. Stop for a senior auditor to confirm or reject the proposed scope. A rejection needs a reason, blocks analysis, and freezes ingest until that senior reopens the scope.
5. Analyze in Python: match, subtract, apply policy limits, score risk. Then phrase the finding.
6. A senior auditor approves, corrects, or rejects. Until then the finding is not an official conclusion.

## Raw versus processed

- Raw row: `field_name`, `value`, `page`, `confidence`, `validation_status` (`validated`, `failed`, `not_found`, `unverified`).
- Processed finding: `rule_id`, Python `delta_amount`, `risk_band`, `explanation`, evidence ids.
- Never replace the raw table with a prose summary.
- Notable fields outside the schema use `validation_status=unverified` and must not feed arithmetic.

## Rules for new checks

- Compute money with integer minor units of the major currency amount (whole PKR in this prototype).
- Store the rule id and the evidence field ids on the finding.
- Wording: "exception requiring investigation".
- If a document is absent, say it was not found in the provided records. Do not invent a violation from a missing file unless the rule explicitly means "missing evidence".

## UI

Keep separate screens for important data, analysis, and review. Important data sits before analysis: extracted field values, page links, and the PDF. Analysis is a separate processed result. Review actions render only for `senior_auditor`. The API must enforce the same rule.
