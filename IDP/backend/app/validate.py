"""Rule-based validation. Flags exceptions for mandatory human review."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_dataset(cleaned: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = cleaned.get("rows") or []
    dtypes: dict[str, str] = cleaned.get("dtypes") or {}
    columns: list[str] = cleaned.get("columns") or []
    key_columns: list[str] = cleaned.get("key_columns") or []

    exceptions: list[dict[str, Any]] = []

    if not rows:
        exceptions.append(
            _exc("EMPTY_DATASET", "high", "No data rows remain after cleaning.", None, None, None)
        )

    if not columns:
        exceptions.append(
            _exc("NO_COLUMNS", "high", "No columns detected for ERP export.", None, None, None)
        )

    # Required key columns must be present and non-empty.
    for key in key_columns:
        if key not in columns:
            exceptions.append(
                _exc("MISSING_KEY_COLUMN", "high", f"Key column '{key}' is not present.", None, key, None)
            )
            continue
        for idx, row in enumerate(rows):
            if _is_empty(row.get(key)):
                exceptions.append(
                    _exc(
                        "MISSING_KEY_VALUE",
                        "high",
                        f"Key column '{key}' is blank.",
                        idx,
                        key,
                        row.get(key),
                    )
                )

    for idx, row in enumerate(rows):
        for col in columns:
            dtype = (dtypes.get(col) or "string").lower()
            value = row.get(col)
            if _is_empty(value):
                continue
            if dtype in {"number", "currency"} and not _is_number(value):
                exceptions.append(
                    _exc("INVALID_NUMBER", "medium", f"Expected {dtype} in '{col}'.", idx, col, value)
                )
            elif dtype == "date" and not _is_iso_date(value):
                exceptions.append(
                    _exc("INVALID_DATE", "medium", f"Expected ISO date in '{col}'.", idx, col, value)
                )
            elif dtype == "boolean" and not isinstance(value, bool):
                exceptions.append(
                    _exc("INVALID_BOOLEAN", "low", f"Expected boolean in '{col}'.", idx, col, value)
                )
            elif "email" in col and isinstance(value, str) and not _EMAIL_RE.match(value):
                exceptions.append(
                    _exc("INVALID_EMAIL", "low", f"Email format looks invalid in '{col}'.", idx, col, value)
                )

    # Duplicate key fingerprint after clean should already be removed; still warn if keys collide loosely.
    if key_columns and rows:
        seen: dict[str, int] = {}
        for idx, row in enumerate(rows):
            fp = "|".join(str(row.get(k, "")) for k in key_columns)
            if not fp.strip("|"):
                continue
            if fp in seen:
                exceptions.append(
                    _exc(
                        "DUPLICATE_KEY",
                        "medium",
                        f"Duplicate key signature also seen at row {seen[fp]}.",
                        idx,
                        ",".join(key_columns),
                        fp,
                    )
                )
            else:
                seen[fp] = idx

    # Surface AI-reported issues that are not already covered.
    for issue in analysis.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "AI_ISSUE")
        if code == "AI_FALLBACK":
            exceptions.append(
                _exc(
                    code,
                    "low",
                    str(issue.get("message") or "AI fallback used."),
                    issue.get("row_hint"),
                    None,
                    None,
                )
            )
            continue
        exceptions.append(
            _exc(
                code,
                "medium",
                str(issue.get("message") or "AI flagged an issue."),
                issue.get("row_hint"),
                None,
                None,
            )
        )

    # Cap volume for review UX while keeping a count.
    max_exceptions = 200
    truncated = max(0, len(exceptions) - max_exceptions)
    exceptions = exceptions[:max_exceptions]

    return {
        "ok": len(exceptions) == 0,
        "exception_count": len(exceptions) + truncated,
        "truncated": truncated,
        "exceptions": exceptions,
        "summary": {
            "rows_checked": len(rows),
            "columns_checked": len(columns),
            "key_columns": key_columns,
        },
    }


def _exc(
    code: str,
    severity: str,
    message: str,
    row_index: Any,
    field_name: str | None,
    value: Any,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "code": code,
        "severity": severity,
        "message": message,
        "row_index": None if row_index is None else int(row_index),
        "field_name": field_name,
        "value": value,
        "status": "pending",
    }


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == ""


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).replace(",", ""))
        return True
    except ValueError:
        return False


def _is_iso_date(value: Any) -> bool:
    text = str(value)
    try:
        datetime.strptime(text[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False
