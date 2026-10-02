"""Apply post-approval note remediations to the cleaned CSV."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def apply_remediations_to_csv(
    clean_path: Path,
    *,
    remediations: list[dict[str, Any]],
    result_path: Path,
) -> dict[str, Any]:
    """Apply set/clear/drop_row remediations; write result CSV. Returns stats."""
    if not clean_path.is_file():
        raise ValueError("Clean table missing for remediation.")

    with clean_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    applied: list[dict[str, Any]] = []
    drop_indexes: set[int] = set()

    for item in remediations:
        action = str(item.get("action") or "")
        row_index = item.get("row_index")
        field = str(item.get("field") or "")
        reason = str(item.get("reason") or "")

        if action == "drop_row":
            if isinstance(row_index, int) and 0 <= row_index < len(rows):
                drop_indexes.add(row_index)
                applied.append({**item, "status": "applied"})
            else:
                applied.append({**item, "status": "skipped", "reason": reason or "invalid row_index"})
            continue

        if not isinstance(row_index, int) or row_index < 0 or row_index >= len(rows):
            applied.append({**item, "status": "skipped", "reason": reason or "invalid row_index"})
            continue
        if field not in rows[row_index] and field not in columns:
            match = next((c for c in columns if c.lower() == field.lower()), None)
            if not match:
                applied.append({**item, "status": "skipped", "reason": f"unknown field '{field}'"})
                continue
            field = match

        if action == "clear":
            rows[row_index][field] = ""
            applied.append({**item, "field": field, "status": "applied"})
        elif action == "set":
            rows[row_index][field] = "" if item.get("value") is None else str(item.get("value"))
            applied.append({**item, "field": field, "status": "applied"})
        else:
            applied.append({**item, "status": "skipped", "reason": f"unknown action '{action}'"})

    kept = [row for idx, row in enumerate(rows) if idx not in drop_indexes]
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in kept:
            writer.writerow({c: row.get(c, "") for c in columns})

    return {
        "columns": columns,
        "row_count": len(kept),
        "rows_dropped": len(drop_indexes),
        "changes_applied": sum(1 for a in applied if a.get("status") == "applied"),
        "applied": applied,
        "result_path": str(result_path),
    }


def read_csv_sample(path: Path, *, limit: int = 12) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({k: ("" if v is None else str(v)) for k, v in row.items()})
            if len(rows) >= limit:
                break
    return columns, rows
