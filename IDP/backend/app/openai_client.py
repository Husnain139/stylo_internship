"""OpenAI client for structure analysis + advisory review checklist. Hard token caps."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .config import (
    openai_api_key,
    openai_max_input_chars,
    openai_max_output_tokens,
    openai_max_sample_rows,
    openai_model,
    openai_temperature,
    openai_timeout_seconds,
)

DOCUMENT_TYPES = (
    "sales_order_lines",
    "sales_orders",
    "purchase_order_lines",
    "purchase_orders",
    "invoice_lines",
    "invoice",
    "credit_note",
    "payment_receipt",
    "bank_statement",
    "general_ledger",
    "journal_entry",
    "trial_balance",
    "payroll",
    "expense_report",
    "inventory",
    "fixed_assets",
    "vendor_master",
    "customer_master",
    "chart_of_accounts",
    "tax_register",
    "other",
)

DOCUMENT_TYPE_LABELS = {
    "sales_order_lines": "Sales order lines",
    "sales_orders": "Sales orders",
    "purchase_order_lines": "Purchase order lines",
    "purchase_orders": "Purchase orders",
    "invoice_lines": "Invoice lines",
    "invoice": "Invoice",
    "credit_note": "Credit note",
    "payment_receipt": "Payment / receipt",
    "bank_statement": "Bank statement",
    "general_ledger": "General ledger",
    "journal_entry": "Journal entry",
    "trial_balance": "Trial balance",
    "payroll": "Payroll",
    "expense_report": "Expense report",
    "inventory": "Inventory",
    "fixed_assets": "Fixed assets",
    "vendor_master": "Vendor master",
    "customer_master": "Customer master",
    "chart_of_accounts": "Chart of accounts",
    "tax_register": "Tax register",
    "other": "Other / unclassified",
}

_DOC_TYPE_SET = set(DOCUMENT_TYPES)

_DTYPES = ("string", "number", "date", "currency", "boolean", "email")

# Column mapping item (shared by analyze schemas)
_COLUMN_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Exact source header from the file",
        },
        "erp_name": {
            "type": "string",
            "description": "snake_case ERP field name",
        },
        "dtype": {
            "type": "string",
            "enum": list(_DTYPES),
            "description": "Normalized data type for validation",
        },
    },
    "required": ["name", "erp_name", "dtype"],
    "additionalProperties": False,
}

_ISSUE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "Short machine code, e.g. MISSING_HEADER"},
        "message": {"type": "string", "description": "Human-readable issue"},
        "row_hint": {
            "type": ["integer", "null"],
            "description": "0-based sample row index if relevant, else null",
        },
    },
    "required": ["code", "message", "row_hint"],
    "additionalProperties": False,
}

_IMPORTANT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Short field or concept name, e.g. Invoice total",
        },
        "value": {
            "type": "string",
            "description": "Observed value from the sample/document, or blank if unknown",
        },
        "why": {
            "type": "string",
            "description": "Why this matters for ERP ingest / human review",
        },
    },
    "required": ["label", "value", "why"],
    "additionalProperties": False,
}

ANALYZE_JSON_SCHEMA = {
    "name": "idp_structure_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "document_type": {
                "type": "string",
                "enum": list(DOCUMENT_TYPES),
                "description": "Business document category, never file format",
            },
            "important_data": {
                "type": "array",
                "items": _IMPORTANT_ITEM_SCHEMA,
                "description": "Up to 8 critical facts/fields for finance review before clean",
            },
            "columns": {"type": "array", "items": _COLUMN_ITEM_SCHEMA},
            "key_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "ERP column names that uniquely identify one import row",
            },
            "issues": {"type": "array", "items": _ISSUE_ITEM_SCHEMA},
            "notes": {"type": "string", "description": "One short sentence"},
        },
        "required": [
            "document_type",
            "important_data",
            "columns",
            "key_columns",
            "issues",
            "notes",
        ],
        "additionalProperties": False,
    },
}

VISION_ANALYZE_JSON_SCHEMA = {
    "name": "idp_vision_structure_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "document_type": {
                "type": "string",
                "enum": list(DOCUMENT_TYPES),
            },
            "important_data": {
                "type": "array",
                "items": _IMPORTANT_ITEM_SCHEMA,
                "description": "Up to 8 critical facts visible on the page",
            },
            "columns": {"type": "array", "items": _COLUMN_ITEM_SCHEMA},
            "key_columns": {"type": "array", "items": {"type": "string"}},
            "issues": {"type": "array", "items": _ISSUE_ITEM_SCHEMA},
            "notes": {"type": "string"},
            "sample_rows": {
                "type": "array",
                "description": "Up to 12 recovered rows; values align with columns[].erp_name order",
                "items": {
                    "type": "object",
                    "properties": {
                        "values": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["values"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "document_type",
            "important_data",
            "columns",
            "key_columns",
            "issues",
            "notes",
            "sample_rows",
        ],
        "additionalProperties": False,
    },
}

REVIEW_JSON_SCHEMA = {
    "name": "idp_review_checklist",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "focus": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 5 concrete review actions",
            },
            "likely_keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 3 ERP uniqueness key columns (composite allowed)",
            },
            "erp_risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 4 import risks",
            },
            "summary": {
                "type": "string",
                "description": "One sentence: document type + what to verify",
            },
        },
        "required": ["focus", "likely_keys", "erp_risks", "summary"],
        "additionalProperties": False,
    },
}

# System prompts: role + labeled policy. Schema enforces shape; keep behavior rules here.
# Critical constraints repeated at the end (recency bias).

SYSTEM_ANALYZE = """# Role
You are an Intelligent Document Processing analyst for Finance & Accounts ERP ingest.

# Task
From the provided table metadata and sample rows only, infer ERP structure:
document type, important_data (critical facts for humans), column mapping, uniqueness keys, and light quality issues.

# How to decide
- document_type = business content (sales lines, bank statement, GL…), NEVER file format (csv/xlsx/pdf).
- important_data: up to 8 items the reviewer must notice first (totals, vendor, invoice id, period, currency, tax). Use values from the sample when present.
- columns[].name must copy source headers exactly; erp_name is snake_case.
- dtype: money→currency, dates→date, emails→email, counts/ids that are numeric→number, else string.
- key_columns must uniquely identify ONE ERP import row.
- Line tables (line number / SalesOrderLineNumber / line_no): use COMPOSITE keys, e.g. sales_order_number + sales_order_line_number.
- Prefer inferred_line_item_keys from the user payload when present.

# Example (pattern only)
Input columns SalesOrderNumber, SalesOrderLineNumber, Quantity →
document_type=sales_order_lines; key_columns=["sales_order_number","sales_order_line_number"]; Quantity is NOT a key.

# Non-goals
Do not invent row values. Do not approve/reject data. Do not rewrite amounts. Max 8 issues. Be concise.

# Critical (must follow)
Never use quantity, amount, tax, price, or email as uniqueness keys. Prefer other over a wrong type only when nothing fits."""

SYSTEM_REVIEW_CHECKLIST = """# Role
You advise a finance reviewer before ERP export. You are advisory only.

# Task
Produce a short human checklist grounded in the supplied columns, dtypes, samples, suggested keys, and python_exception_codes.

# How to decide
- focus: concrete checks the reviewer can do (max 5). Prioritize python_exception_codes and key integrity.
- likely_keys: true ERP uniqueness columns (composite for line items). Prefer suggested_keys / inferred_line_item_keys.
- erp_risks: what breaks ERP import if ignored (max 4).
- summary: one sentence naming document type and the main verification goal.
- If a line-number column exists, say verify unique (order + line) pairs — never "unique order numbers alone".

# Non-goals
Do not pass/fail. Do not invent figures, row counts, or columns that are not provided. Do not claim Python validation results beyond listed exception codes.

# Critical (must follow)
Never list quantity, amount, tax, unit_price, or email as likely_keys. Stay advisory."""

SYSTEM_REMEDIATE = """# Role
You turn human approval notes and review checklist steps into precise row fixes for a cleaned finance CSV.

# Task
Given columns, exception rows (with notes), and checklist steps, output remediations only when the note/step clearly asks for a data change.

# How to decide
- action set: replace a field value; clear: blank a field; drop_row: remove the row.
- Prefer row_index from the exception when present.
- Only change values the note explicitly supports. Never invent amounts or IDs.
- If a note only says "OK" / "approved" with no fix, skip it.
- Checklist steps that are review-only (no concrete value change) produce no remediation.

# Critical (must follow)
Do not invent figures. Prefer zero remediations over unsafe guesses."""

REMEDIATE_JSON_SCHEMA = {
    "name": "idp_post_approval_remediation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "remediations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "row_index": {"type": ["integer", "null"]},
                        "field": {"type": "string"},
                        "action": {"type": "string", "enum": ["set", "clear", "drop_row"]},
                        "value": {"type": ["string", "null"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["row_index", "field", "action", "value", "reason"],
                    "additionalProperties": False,
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["remediations", "summary"],
        "additionalProperties": False,
    },
}

_WEAK_KEY_TOKENS = (
    "quantity",
    "qty",
    "amount",
    "tax",
    "price",
    "unit_price",
    "total",
    "email",
    "emailaddress",
    "name",
    "customername",
    "item",
    "description",
)


class OpenAIConfigError(RuntimeError):
    pass


def truncate(text: str, limit: int | None = None) -> str:
    cap = limit if limit is not None else openai_max_input_chars()
    text = text or ""
    if len(text) <= cap:
        return text
    return text[: max(0, cap - 18)] + "\n…[truncated]"


def _parse_json(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError("model did not return valid JSON")


def _snake(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    return (text or "field")[:64]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def infer_key_columns(columns: list[str]) -> list[str]:
    """Deterministic composite-key hints for common ERP line tables."""
    if not columns:
        return []
    by_norm = {_norm(c): c for c in columns}
    snakes = {_snake(c): c for c in columns}

    def find(*needles: str) -> str | None:
        for n in needles:
            if n in by_norm:
                return by_norm[n]
            if n in snakes:
                return snakes[n]
            for col in columns:
                if n in _norm(col) or n in _snake(col):
                    return col
        return None

    order = find(
        "salesordernumber",
        "sales_order_number",
        "ordernumber",
        "order_number",
        "invoicenumber",
        "invoice_number",
        "ponumber",
        "po_number",
    )
    line = find(
        "salesorderlinenumber",
        "sales_order_line_number",
        "linenumber",
        "line_number",
        "lineno",
        "line_no",
        "orderlinenumber",
    )
    if order and line and order != line:
        return [_snake(order), _snake(line)]

    for token in ("id", "code", "sku", "vendorid", "customerid", "employeeid"):
        hit = find(token)
        if hit:
            return [_snake(hit)]

    return [_snake(columns[0])]


def _filter_weak_keys(keys: list[str], columns: list[str], fallback: list[str]) -> list[str]:
    col_set = {_snake(c) for c in columns} | set(columns)
    cleaned: list[str] = []
    for key in keys:
        sk = _snake(key)
        if sk not in col_set and key not in col_set:
            # allow snake forms that match column snakes
            if sk not in {_snake(c) for c in columns}:
                continue
        if any(tok in _norm(sk) for tok in _WEAK_KEY_TOKENS):
            continue
        if sk not in cleaned:
            cleaned.append(sk)
    # Prefer deterministic composite line-item keys when AI omitted the line part.
    fb = [k for k in fallback if k][:3]
    if len(fb) >= 2 and (not cleaned or (len(cleaned) == 1 and cleaned[0] == fb[0])):
        return fb
    if cleaned:
        return cleaned[:3]
    return fb or infer_key_columns(columns)[:3]


def _guess_dtype(name: str) -> str:
    n = _norm(name)
    if "email" in n:
        return "email"
    if any(t in n for t in ("date", "dob", "timestamp")):
        return "date"
    if any(t in n for t in ("amount", "price", "tax", "cost", "total", "fee")):
        return "currency"
    if any(t in n for t in ("qty", "quantity", "count", "number", "line")):
        return "number"
    return "string"


def analyze_structure(extracted: dict[str, Any]) -> dict[str, Any]:
    """Call gpt-4o-mini for structure hints. Falls back to local heuristic on failure.

    Vision/scan documents require OpenAI — heuristic cannot invent a usable table.
    """
    needs_vision = bool(extracted.get("needs_vision") and extracted.get("file_b64"))
    try:
        return _analyze_with_openai(extracted)
    except Exception as exc:  # noqa: BLE001 — controlled fallback for desk continuity
        if needs_vision:
            raise
        return _heuristic_analysis(extracted, error=str(exc))


def materialize_vision_table(extracted: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    """Force OpenAI vision recovery of a tabular extract. Raises if unusable."""
    if not extracted.get("file_b64"):
        raise ValueError("No image payload available for OpenAI vision recovery.")
    if not openai_api_key():
        raise OpenAIConfigError(
            "OPENAI_API_KEY is not set. Scanned PDFs/images need OpenAI to build the raw table."
        )
    analysis = _analyze_with_openai({**extracted, "needs_vision": True})
    cols = list(analysis.get("_vision_columns") or [])
    rows = list(analysis.get("_vision_rows") or [])
    if not rows:
        # Second pass with a stronger instruction + more tokens.
        analysis = _recover_vision_table(extracted)
        cols = list(analysis.get("_vision_columns") or [])
        rows = list(analysis.get("_vision_rows") or [])
    if not rows or not cols:
        raise ValueError(
            "OpenAI vision could not recover any table rows from this scan. "
            "Try a clearer image/PDF page, or upload CSV/Excel."
        )
    return cols, rows, analysis


def _vision_rows_from_parsed(parsed: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    cols = [
        str(c.get("erp_name") or c.get("name") or "").strip()
        for c in (parsed.get("columns") or [])
        if isinstance(c, dict)
    ]
    cols = [c for c in cols if c]
    rows: list[dict[str, Any]] = []
    for item in parsed.get("sample_rows") or []:
        if not isinstance(item, dict):
            continue
        values = item.get("values")
        if isinstance(values, list) and cols:
            rows.append(
                {
                    cols[i]: ("" if i >= len(values) or values[i] is None else str(values[i]))
                    for i in range(len(cols))
                }
            )
        elif cols and any(k in item for k in cols):
            rows.append({k: item.get(k, "") for k in cols})
    return cols, rows


def _recover_vision_table(extracted: dict[str, Any]) -> dict[str, Any]:
    text = (
        "CRITICAL: Extract every readable finance table row from this page.\n"
        "Return columns with erp_name snake_case, then sample_rows with values[] "
        "aligned to that column order (at least 1 data row if any numbers/text are visible).\n"
        "Do not return an empty sample_rows unless the page is blank."
    )
    user_content: Any = [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{extracted.get('mime', 'image/png')};base64,{extracted['file_b64']}",
                "detail": "high" if extracted.get("kind") == "image" else "low",
            },
        },
    ]
    parsed, meta = _chat_json(
        system=SYSTEM_ANALYZE,
        user=user_content,
        json_schema=VISION_ANALYZE_JSON_SCHEMA,
        max_tokens=1024,
    )
    parsed["_meta"] = {**meta, "recovery_pass": True}
    cols, rows = _vision_rows_from_parsed(parsed)
    if rows:
        parsed["_vision_rows"] = rows
        parsed["_vision_columns"] = cols or list(rows[0].keys())
    return parsed


def review_checklist(
    *,
    columns: list[str],
    sample_rows: list[dict[str, Any]],
    key_columns: list[str],
    exception_codes: list[str],
    row_count: int,
    document_type: str | None = None,
    dtypes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Advisory checklist for human review. Never decides validation outcomes."""
    try:
        return _review_with_openai(
            columns=columns,
            sample_rows=sample_rows,
            key_columns=key_columns,
            exception_codes=exception_codes,
            row_count=row_count,
            document_type=document_type,
            dtypes=dtypes or {},
        )
    except Exception as exc:  # noqa: BLE001
        return _heuristic_checklist(
            columns=columns,
            key_columns=key_columns,
            exception_codes=exception_codes,
            document_type=document_type,
            dtypes=dtypes or {},
            error=str(exc),
        )


def plan_remediations_from_notes(
    *,
    columns: list[str],
    exception_notes: list[dict[str, Any]],
    checklist_steps: list[str],
    sample_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Turn approval notes + checklist steps into concrete CSV remediations."""
    if not any(str(e.get("note") or "").strip() for e in exception_notes) and not any(
        str(s).strip() for s in checklist_steps
    ):
        return {"remediations": [], "summary": "No actionable notes or checklist steps.", "_meta": {"provider": "skip"}}

    try:
        payload = {
            "columns": columns,
            "exception_notes": exception_notes[:40],
            "checklist_steps": checklist_steps[:8],
            "sample_rows": sample_rows[:8],
        }
        parsed, meta = _chat_json(
            system=SYSTEM_REMEDIATE,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            json_schema=REMEDIATE_JSON_SCHEMA,
            max_tokens=768,
        )
        remediations = []
        col_set = {str(c) for c in columns}
        for item in parsed.get("remediations") or []:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "")
            field = str(item.get("field") or "")
            if action == "drop_row":
                remediations.append(
                    {
                        "row_index": item.get("row_index"),
                        "field": field or "",
                        "action": "drop_row",
                        "value": None,
                        "reason": str(item.get("reason") or ""),
                    }
                )
                continue
            if field not in col_set:
                # case-insensitive match
                match = next((c for c in columns if c.lower() == field.lower()), None)
                if not match:
                    continue
                field = match
            remediations.append(
                {
                    "row_index": item.get("row_index"),
                    "field": field,
                    "action": action if action in {"set", "clear", "drop_row"} else "set",
                    "value": None if action == "clear" else (None if item.get("value") is None else str(item.get("value"))),
                    "reason": str(item.get("reason") or ""),
                }
            )
        return {
            "remediations": remediations,
            "summary": str(parsed.get("summary") or ""),
            "_meta": meta,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "remediations": [],
            "summary": f"Could not plan remediations from notes ({exc}).",
            "_meta": {"provider": "heuristic", "error": str(exc)[:300]},
        }


def _chat_json(
    *,
    system: str,
    user: str | list[dict[str, Any]],
    json_schema: dict[str, Any],
    max_tokens: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = openai_api_key()
    if not api_key:
        raise OpenAIConfigError("OPENAI_API_KEY is not set")
    host = urlparse("https://api.openai.com/v1/chat/completions").hostname
    if host != "api.openai.com":
        raise OpenAIConfigError(f"disallowed host: {host}")

    user_content: Any
    if isinstance(user, str):
        user_content = truncate(user)
    elif isinstance(user, list):
        # Multimodal: truncate only text parts
        user_content = []
        for part in user:
            if isinstance(part, dict) and part.get("type") == "text":
                user_content.append({**part, "text": truncate(str(part.get("text") or ""))})
            else:
                user_content.append(part)
    else:
        user_content = truncate(str(user))

    body = {
        "model": openai_model(),
        "temperature": openai_temperature(),
        "max_tokens": max(64, min(2048, max_tokens or openai_max_output_tokens())),
        "response_format": {
            "type": "json_schema",
            "json_schema": json_schema,
        },
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=openai_timeout_seconds()) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        # Fallback: older snapshots may reject json_schema — retry once with json_object.
        if exc.code == 400 and "json_schema" in detail.lower():
            return _chat_json_loose(system=system, user=user_content, max_tokens=max_tokens)
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("OpenAI request timed out") from exc

    message = raw["choices"][0]["message"]
    if message.get("refusal"):
        raise RuntimeError(f"OpenAI refused: {message['refusal']}")
    content = message.get("content") or ""
    parsed = _parse_json(content)
    usage = raw.get("usage") or {}
    meta = {
        "model": openai_model(),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "provider": "openai",
        "response_format": "json_schema",
    }
    return parsed, meta


def _chat_json_loose(
    *,
    system: str,
    user: Any,
    max_tokens: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compatibility fallback when strict json_schema is unavailable."""
    body = {
        "model": openai_model(),
        "temperature": openai_temperature(),
        "max_tokens": max(64, min(2048, max_tokens or openai_max_output_tokens())),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system + "\n\nRespond with a single JSON object only."},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=openai_timeout_seconds()) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    parsed = _parse_json(content)
    usage = raw.get("usage") or {}
    meta = {
        "model": openai_model(),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "provider": "openai",
        "response_format": "json_object",
    }
    return parsed, meta


def _review_with_openai(
    *,
    columns: list[str],
    sample_rows: list[dict[str, Any]],
    key_columns: list[str],
    exception_codes: list[str],
    row_count: int,
    document_type: str | None,
    dtypes: dict[str, str],
) -> dict[str, Any]:
    inferred = infer_key_columns(columns)
    suggested = _filter_weak_keys(list(key_columns or []), columns, inferred)
    payload = {
        "task": "Build an advisory ERP review checklist for this cleaned table.",
        "document_type": document_type or "other",
        "columns": columns[:40],
        "dtypes": {k: dtypes.get(k, "string") for k in columns[:40]},
        "sample_rows": (sample_rows or [])[: min(8, openai_max_sample_rows())],
        "suggested_keys": suggested,
        "inferred_line_item_keys": inferred,
        "python_exception_codes": list(dict.fromkeys(exception_codes))[:12],
        "row_count": row_count,
    }
    user = (
        json.dumps(payload, ensure_ascii=False, default=str)
        + "\n\nReminder: advisory only; use suggested_keys when line-item composite; "
        "never use quantity/email/amount as keys."
    )
    parsed, meta = _chat_json(
        system=SYSTEM_REVIEW_CHECKLIST,
        user=user,
        json_schema=REVIEW_JSON_SCHEMA,
        max_tokens=400,
    )
    keys = _filter_weak_keys(
        [str(x) for x in (parsed.get("likely_keys") or []) if str(x).strip()],
        columns,
        suggested,
    )
    return {
        "focus": [str(x) for x in (parsed.get("focus") or []) if str(x).strip()][:5],
        "likely_keys": keys,
        "erp_risks": [str(x) for x in (parsed.get("erp_risks") or []) if str(x).strip()][:4],
        "summary": str(parsed.get("summary") or "").strip()[:280],
        "advisory_only": True,
        "_meta": meta,
    }


def _heuristic_checklist(
    *,
    columns: list[str],
    key_columns: list[str],
    exception_codes: list[str],
    document_type: str | None,
    dtypes: dict[str, str],
    error: str,
) -> dict[str, Any]:
    keys = _filter_weak_keys(list(key_columns or []), columns, infer_key_columns(columns))
    focus: list[str] = []
    if exception_codes:
        focus.append(f"Review Python exceptions: {', '.join(list(dict.fromkeys(exception_codes))[:5])}")
    if len(keys) >= 2:
        focus.append(f"Confirm composite key uniqueness: {' + '.join(keys)}")
    elif keys:
        focus.append(f"Confirm business key column: {keys[0]}")
    else:
        focus.append("Confirm which column uniquely identifies each ERP row")

    col_norm = {_norm(c): c for c in columns}
    if any("email" in n for n in col_norm):
        focus.append("Check email address format on customer/contact columns")
    if any(t in n for n in col_norm for t in ("qty", "quantity")):
        focus.append("Ensure quantity is a positive number")
    if any(t in n for n in col_norm for t in ("tax", "unitprice", "price")):
        focus.append("Spot-check tax against unit price x expected rate")

    risks = []
    if len(keys) >= 2:
        risks.append("Duplicate order+line pairs breaking ERP import")
    else:
        risks.append("Duplicate or missing key values on import")
    if any("email" in n for n in col_norm):
        risks.append("Invalid email addresses")
    if any("tax" in n for n in col_norm):
        risks.append("Incorrect tax vs price calculations")

    doc = document_type or "tabular ledger"
    return {
        "focus": focus[:5],
        "likely_keys": keys[:3],
        "erp_risks": risks[:4] or ["AI checklist unavailable; use Python exceptions"],
        "summary": f"Local advisory checklist for {doc} (AI unavailable).",
        "advisory_only": True,
        "_meta": {"provider": "heuristic", "model": None, "error": error[:300]},
    }


def _analyze_with_openai(extracted: dict[str, Any]) -> dict[str, Any]:
    source_cols = [str(c) for c in (extracted.get("columns") or [])]
    inferred_keys = infer_key_columns(source_cols)
    inferred_doc = infer_document_type(source_cols)
    vision = bool(extracted.get("needs_vision") and extracted.get("file_b64"))

    if vision:
        text = (
            "Task: recover a finance table from this scanned page (low detail).\n"
            f"Hint keys if line items: {inferred_keys}. Hint type: {inferred_doc}.\n"
            "Put recovered rows in sample_rows[].values aligned to columns[].erp_name order "
            "(max 12). Prefer real visible values; leave issues if unsure — but return rows "
            "whenever any table/line items are readable.\n"
            "Critical: do not invent amounts."
        )
        user_content: Any = [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{extracted.get('mime', 'image/png')};base64,{extracted['file_b64']}",
                    "detail": "high" if extracted.get("kind") == "image" else "low",
                },
            },
        ]
        schema = VISION_ANALYZE_JSON_SCHEMA
    else:
        sample = extracted.get("sample_rows") or extracted.get("rows") or []
        sample = sample[: openai_max_sample_rows()]
        payload = {
            "task": "Infer ERP structure for this tabular extract.",
            "kind": extracted.get("kind"),
            "sheet_name": extracted.get("sheet_name"),
            "columns": source_cols,
            "row_count": extracted.get("row_count", len(extracted.get("rows") or [])),
            "sample_rows": sample,
            "notes": extracted.get("notes"),
            "inferred_line_item_keys": inferred_keys,
            "inferred_document_type": inferred_doc,
        }
        user_content = (
            json.dumps(payload, ensure_ascii=False, default=str)
            + "\n\nReminder: classify by business content not file format; "
            "prefer inferred_line_item_keys for composite uniqueness; never key on qty/email/amount."
        )
        schema = ANALYZE_JSON_SCHEMA

    parsed, meta = _chat_json(
        system=SYSTEM_ANALYZE,
        user=user_content,
        json_schema=schema,
        max_tokens=1024 if vision else openai_max_output_tokens(),
    )
    parsed["_meta"] = meta

    # Prefer composite line-item keys when columns clearly indicate them.
    erp_names = []
    for col in parsed.get("columns") or []:
        if isinstance(col, dict):
            erp_names.append(str(col.get("erp_name") or _snake(col.get("name") or "")))
    if not erp_names:
        erp_names = [_snake(c) for c in source_cols]
    forced = infer_key_columns(erp_names if erp_names else source_cols)
    ai_keys = [str(k) for k in (parsed.get("key_columns") or []) if str(k).strip()]
    parsed["key_columns"] = _filter_weak_keys(ai_keys, erp_names or source_cols, forced)

    parsed["document_type"] = normalize_document_type(parsed.get("document_type"))
    if parsed["document_type"] == "other" and inferred_doc != "other":
        parsed["document_type"] = inferred_doc
    parsed["document_type_label"] = document_type_label(parsed["document_type"])
    parsed["important_data"] = _normalize_important_data(parsed.get("important_data"))

    # Vision: sample_rows[].values aligned to erp column order (strict schema).
    if vision:
        cols, rows = _vision_rows_from_parsed(parsed)
        if rows:
            parsed["_vision_rows"] = rows
            parsed["_vision_columns"] = cols or list(rows[0].keys())
    return parsed


def _normalize_important_data(raw: object) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        out.append(
            {
                "label": label[:120],
                "value": str(item.get("value") or "").strip()[:240],
                "why": str(item.get("why") or "").strip()[:240],
            }
        )
    return out


def order_line_document(columns: list[str]) -> bool:
    keys = infer_key_columns(columns)
    return len(keys) >= 2


def normalize_document_type(value: object) -> str:
    raw = _snake(str(value or "")).replace("-", "_")
    aliases = {
        "sales_order": "sales_orders",
        "sales_lines": "sales_order_lines",
        "sales": "sales_order_lines",
        "purchase_order": "purchase_orders",
        "po_lines": "purchase_order_lines",
        "purchase_lines": "purchase_order_lines",
        "ap_invoice": "invoice",
        "ar_invoice": "invoice",
        "invoice_line": "invoice_lines",
        "credit_memo": "credit_note",
        "receipt": "payment_receipt",
        "payment": "payment_receipt",
        "bank": "bank_statement",
        "statement": "bank_statement",
        "gl": "general_ledger",
        "ledger": "general_ledger",
        "journal": "journal_entry",
        "journals": "journal_entry",
        "tb": "trial_balance",
        "expense": "expense_report",
        "expenses": "expense_report",
        "stock": "inventory",
        "vendor": "vendor_master",
        "suppliers": "vendor_master",
        "supplier_master": "vendor_master",
        "customer": "customer_master",
        "customers": "customer_master",
        "coa": "chart_of_accounts",
        "accounts": "chart_of_accounts",
        "tax": "tax_register",
        "vat_register": "tax_register",
        "asset": "fixed_assets",
        "assets": "fixed_assets",
        "salary": "payroll",
        "wages": "payroll",
    }
    if raw in _DOC_TYPE_SET:
        return raw
    if raw in aliases:
        return aliases[raw]
    for key, mapped in aliases.items():
        if key in raw:
            return mapped
    return "other"


def infer_document_type(columns: list[str]) -> str:
    """Column-name heuristic when AI returns other or is unavailable."""
    joined = " ".join(_norm(c) for c in columns)
    tokens = {_norm(c) for c in columns}

    def has(*needles: str) -> bool:
        return any(n in joined or any(n in t for t in tokens) for n in needles)

    lineish = order_line_document(columns) or has("linenumber", "lineno", "line_no", "orderline")

    if has("bank", "iban", "swift", "openingbalance", "closingbalance") and has(
        "debit", "credit", "balance", "transaction"
    ):
        return "bank_statement"
    if has("trialbalance") or (has("debit", "credit") and has("account") and not lineish):
        if has("trial"):
            return "trial_balance"
    if has("journal", "jeno", "journalentry"):
        return "journal_entry"
    if has("generalledger", "glaccount") or (has("accountcode", "accountname") and has("debit", "credit")):
        return "general_ledger"
    if has("payroll", "grosspay", "netpay", "salary", "wage"):
        return "payroll"
    if has("expense", "reimburs", "mileage"):
        return "expense_report"
    if has("fixedasset", "assetid", "depreciation", "accumulateddepr"):
        return "fixed_assets"
    if has("sku", "onhand", "warehouse", "stockqty", "inventory"):
        return "inventory"
    if has("chartofaccount", "accounttype") and has("account") and not has("debit", "credit", "amount"):
        return "chart_of_accounts"
    if has("vendorid", "supplierid", "vendorname", "suppliername") and not has("amount", "quantity", "invoice"):
        return "vendor_master"
    if has("customerid", "customername") and not has("quantity", "unitprice", "salesorder"):
        return "customer_master"
    if has("taxcode", "vat", "gst", "withholding") and has("amount", "tax"):
        return "tax_register"
    if has("creditnote", "creditmemo"):
        return "credit_note"
    if has("payment", "receipt", "paidamount", "remittance"):
        return "payment_receipt"
    if has("purchaseorder", "ponumber") and lineish:
        return "purchase_order_lines"
    if has("purchaseorder", "ponumber"):
        return "purchase_orders"
    if has("invoiceline") or (has("invoice") and lineish):
        return "invoice_lines"
    if has("invoice"):
        return "invoice"
    if has("salesorder") and lineish:
        return "sales_order_lines"
    if has("salesorder", "orderdate") and has("customer"):
        return "sales_orders" if not lineish else "sales_order_lines"
    if lineish and has("quantity", "unitprice", "item"):
        return "sales_order_lines"
    return "other"


def document_type_label(value: object) -> str:
    key = normalize_document_type(value)
    return DOCUMENT_TYPE_LABELS.get(key, DOCUMENT_TYPE_LABELS["other"])


def _heuristic_analysis(extracted: dict[str, Any], *, error: str) -> dict[str, Any]:
    columns = extracted.get("columns") or []
    mapped = []
    for name in columns:
        erp = _snake(str(name))
        mapped.append({"name": name, "erp_name": erp, "dtype": _guess_dtype(str(name))})
    erp_cols = [m["erp_name"] for m in mapped]
    source_cols = [str(c) for c in columns]
    keys = infer_key_columns(erp_cols or source_cols)
    doc = infer_document_type(source_cols)
    sample = (extracted.get("sample_rows") or extracted.get("rows") or [])[:1]
    first = sample[0] if sample and isinstance(sample[0], dict) else {}
    important: list[dict[str, str]] = []
    for key in keys[:4]:
        # map erp back to source when possible
        src = next((m["name"] for m in mapped if m["erp_name"] == key), key)
        important.append(
            {
                "label": str(src),
                "value": "" if first.get(src) is None else str(first.get(src)),
                "why": "Likely uniqueness / identity field for ERP import",
            }
        )
    for name in source_cols:
        low = str(name).lower()
        if any(t in low for t in ("amount", "total", "vendor", "invoice", "currency", "date")) and len(important) < 8:
            if any(i["label"] == str(name) for i in important):
                continue
            important.append(
                {
                    "label": str(name),
                    "value": "" if first.get(name) is None else str(first.get(name)),
                    "why": "Common finance field to verify before clean",
                }
            )
    return {
        "document_type": doc,
        "document_type_label": document_type_label(doc),
        "important_data": important[:8],
        "columns": mapped,
        "key_columns": keys,
        "issues": [
            {
                "code": "AI_FALLBACK",
                "message": f"AI analysis unavailable ({error[:160]}); used local heuristic.",
                "row_hint": None,
            }
        ],
        "notes": "Local heuristic schema mapping with document-type inference.",
        "_meta": {"provider": "heuristic", "model": None, "error": error[:300]},
    }
