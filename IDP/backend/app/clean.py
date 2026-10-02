"""Deterministic clean & standardize stage."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


_CURRENCY_RE = re.compile(r"[^\d.\-]")
_MULTI_SPACE = re.compile(r"\s+")


def clean_and_standardize(
    rows: list[dict[str, Any]],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    column_map = {}
    dtypes = {}
    for col in analysis.get("columns") or []:
        if not isinstance(col, dict):
            continue
        src = col.get("name")
        erp = col.get("erp_name") or _snake(str(src or "field"))
        if src:
            column_map[str(src)] = erp
        dtypes[erp] = (col.get("dtype") or "string").lower()

    if not column_map and rows:
        for key in rows[0].keys():
            column_map[key] = _snake(str(key))
            dtypes[column_map[key]] = "string"

    cleaned: list[dict[str, Any]] = []
    blank_removed = 0
    for row in rows:
        remapped: dict[str, Any] = {}
        for src, erp in column_map.items():
            remapped[erp] = _coerce(row.get(src, ""), dtypes.get(erp, "string"))
        # Keep unexpected columns under snake_case for auditability.
        for src, value in row.items():
            if src not in column_map:
                remapped[_snake(str(src))] = _as_string(value)

        if _is_blank_row(remapped):
            blank_removed += 1
            continue
        cleaned.append(remapped)

    before = len(cleaned)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates_removed = 0
    key_cols = [k for k in (analysis.get("key_columns") or []) if isinstance(k, str)]
    if not key_cols and cleaned:
        key_cols = list(cleaned[0].keys())

    for row in cleaned:
        fingerprint = "|".join(str(row.get(k, "")) for k in key_cols) if key_cols else json_fingerprint(row)
        if fingerprint in seen:
            duplicates_removed += 1
            continue
        seen.add(fingerprint)
        deduped.append(row)

    columns = list(deduped[0].keys()) if deduped else list(column_map.values())
    return {
        "columns": columns,
        "rows": deduped,
        "row_count": len(deduped),
        "stats": {
            "input_rows": len(rows),
            "blank_rows_removed": blank_removed,
            "duplicates_removed": duplicates_removed,
            "output_rows": len(deduped),
            "rows_before_dedupe": before,
        },
        "column_map": column_map,
        "dtypes": dtypes,
        "key_columns": key_cols,
    }


def json_fingerprint(row: dict[str, Any]) -> str:
    return "|".join(f"{k}={row.get(k, '')}" for k in sorted(row.keys()))


def _snake(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:64] or "field"


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    return _MULTI_SPACE.sub(" ", str(value)).strip()


def _coerce(value: Any, dtype: str) -> Any:
    if value is None:
        return ""
    if dtype in {"number", "currency"}:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if dtype == "currency" or isinstance(value, float) else value
        text = _as_string(value)
        if not text:
            return ""
        text = text.replace(",", "")
        if dtype == "currency":
            text = _CURRENCY_RE.sub("", text)
        try:
            num = float(text)
            return int(num) if num.is_integer() and dtype == "number" else round(num, 2)
        except ValueError:
            return text
    if dtype == "date":
        text = _as_string(value)
        if not text:
            return ""
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(text[:10], fmt).date().isoformat()
            except ValueError:
                continue
        return text
    if dtype == "boolean":
        text = _as_string(value).lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
        return text
    return _as_string(value)


def _is_blank_row(row: dict[str, Any]) -> bool:
    for value in row.values():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if value == "":
            continue
        return False
    return True
