"""Export ERP-ready CSV / Excel files."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from .config import xlsx_max_rows


def export_erp_files(
    cleaned: dict[str, Any],
    *,
    export_dir: Path,
    job_id: str,
    basename: str,
) -> dict[str, Any]:
    export_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(basename) or "export"
    columns: list[str] = cleaned.get("columns") or []
    rows: list[dict[str, Any]] = cleaned.get("rows") or []

    csv_path = export_dir / f"{job_id}_{stem}.csv"
    xlsx_path = export_dir / f"{job_id}_{stem}.xlsx"

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})

    formats = ["csv"]
    xlsx_skipped_reason = None
    if len(rows) <= xlsx_max_rows():
        _write_xlsx(xlsx_path, columns, rows)
        formats.append("xlsx")
    else:
        xlsx_path.unlink(missing_ok=True)
        xlsx_skipped_reason = (
            f"XLSX skipped - {len(rows):,} rows exceed the {xlsx_max_rows():,} row desk limit. Use CSV."
        )

    return {
        "csv_path": str(csv_path),
        "xlsx_path": str(xlsx_path) if "xlsx" in formats else None,
        "row_count": len(rows),
        "columns": columns,
        "formats": formats,
        "xlsx_skipped_reason": xlsx_skipped_reason,
    }


def export_from_clean_csv(
    clean_csv: Path,
    *,
    columns: list[str],
    export_dir: Path,
    job_id: str,
    basename: str,
    row_count: int | None = None,
) -> dict[str, Any]:
    """Copy disk-backed clean CSV; build XLSX only when under the row cap."""
    export_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(basename) or "export"
    csv_path = export_dir / f"{job_id}_{stem}.csv"
    xlsx_path = export_dir / f"{job_id}_{stem}.xlsx"

    shutil.copyfile(clean_csv, csv_path)

    fieldnames = list(columns)
    counted = 0
    with clean_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not fieldnames:
            fieldnames = list(reader.fieldnames or [])
        for _ in reader:
            counted += 1

    if row_count is None:
        row_count = counted

    formats = ["csv"]
    xlsx_skipped_reason = None
    if row_count <= xlsx_max_rows():
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("ERP")
        ws.append(fieldnames)
        with clean_csv.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ws.append([row.get(c, "") for c in fieldnames])
        wb.save(xlsx_path)
        formats.append("xlsx")
    else:
        xlsx_path.unlink(missing_ok=True)
        xlsx_skipped_reason = (
            f"XLSX skipped - {row_count:,} rows exceed the {xlsx_max_rows():,} row desk limit. Use CSV."
        )

    return {
        "csv_path": str(csv_path),
        "xlsx_path": str(xlsx_path) if "xlsx" in formats else None,
        "row_count": row_count,
        "columns": fieldnames,
        "formats": formats,
        "xlsx_skipped_reason": xlsx_skipped_reason,
    }


def _write_xlsx(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "ERP"
    ws.append(columns)
    for row in rows:
        ws.append([row.get(c, "") for c in columns])
    wb.save(path)


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return cleaned[:80].strip("_")
