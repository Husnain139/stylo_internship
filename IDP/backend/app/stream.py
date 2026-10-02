"""Disk-backed streaming + DuckDB clean/validate for large IDP uploads."""

from __future__ import annotations

import csv
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import data_dir, idp_sample_rows, max_non_tabular_bytes
from .duck import duck_connection, quote_ident, quote_path


def tables_dir() -> Path:
    path = data_dir() / "tables"
    path.mkdir(parents=True, exist_ok=True)
    return path


def table_paths(job_id: str) -> tuple[Path, Path]:
    base = tables_dir()
    return base / f"{job_id}.raw.csv", base / f"{job_id}.clean.csv"


def _normalize_header(value: object, index: int) -> str:
    text = str(value or "").strip()
    if not text:
        return f"col_{index + 1}"
    text = re.sub(r"\s+", " ", text)
    return text[:80]


def _unique_headers(raw_headers: list[object]) -> list[str]:
    seen: dict[str, int] = {}
    columns: list[str] = []
    for i, cell in enumerate(raw_headers):
        name = _normalize_header(cell, i)
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        columns.append(name)
    return columns


def _snake(name: str) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:64] or "field"


def iter_csv_dicts(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {k: ("" if v is None else str(v)) for k, v in row.items()}


def read_sample(path: Path, *, limit: int | None = None) -> tuple[list[str], list[dict[str, str]], int]:
    limit = idp_sample_rows() if limit is None else limit
    columns: list[str] = []
    sample: list[dict[str, str]] = []
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        for row in reader:
            count += 1
            if len(sample) < limit:
                sample.append({k: ("" if v is None else str(v)) for k, v in row.items()})
    return columns, sample, count


def write_dicts_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def materialize_upload(path: Path, *, filename: str, job_id: str) -> dict[str, Any]:
    """Stream CSV/Excel onto disk; return metadata + sample only."""
    suffix = Path(filename).suffix.lower()
    raw_path, _ = table_paths(job_id)
    sample_limit = idp_sample_rows()
    if suffix == ".csv":
        columns, sample, row_count, sheet, kind = _materialize_csv(path, raw_path, sample_limit)
        return {
            "kind": kind,
            "sheet_name": sheet,
            "columns": columns,
            "row_count": row_count,
            "sample_rows": sample,
            "disk_backed": True,
            "raw_table": raw_path.name,
            "needs_vision": False,
        }
    if suffix in {".xlsx", ".xls"}:
        columns, sample, row_count, sheet, kind = _materialize_excel(path, raw_path, sample_limit)
        return {
            "kind": kind,
            "sheet_name": sheet,
            "columns": columns,
            "row_count": row_count,
            "sample_rows": sample,
            "disk_backed": True,
            "raw_table": raw_path.name,
            "needs_vision": False,
        }

    # Word/PDF/image — extract then spill; preserve vision payload when needed.
    size = path.stat().st_size
    if size > max_non_tabular_bytes():
        raise ValueError(
            f"PDF/Word/image uploads are limited to {max_non_tabular_bytes() // (1024 * 1024)} MB. "
            "Convert large ledgers to CSV/Excel."
        )
    from .extractors import extract_document

    extracted = extract_document(path, filename=filename)
    columns = list(extracted.get("columns") or [])
    rows = list(extracted.get("rows") or [])
    needs_vision = bool(extracted.get("needs_vision"))
    if columns:
        write_dicts_csv(raw_path, columns, rows)
    elif not needs_vision:
        # Empty non-vision extract — still write a headerless placeholder.
        write_dicts_csv(raw_path, ["text"], [])
        columns = ["text"]

    return {
        "kind": extracted.get("kind"),
        "sheet_name": extracted.get("sheet_name"),
        "columns": columns,
        "row_count": len(rows),
        "sample_rows": rows[:sample_limit],
        "notes": extracted.get("notes"),
        "disk_backed": True,
        "raw_table": raw_path.name if columns or not needs_vision else None,
        "needs_vision": needs_vision,
        "file_b64": extracted.get("file_b64") if needs_vision else None,
        "mime": extracted.get("mime") if needs_vision else None,
    }


def _materialize_csv(path: Path, dest: Path, sample_limit: int) -> tuple[list[str], list[dict], int, str, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    sample: list[dict[str, str]] = []
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as src, dest.open("w", encoding="utf-8", newline="") as out:
        reader = csv.reader(src)
        try:
            header = next(reader)
        except StopIteration:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("w", encoding="utf-8", newline="") as empty:
                empty.write("")
            return [], [], 0, "csv", "csv"
        columns = _unique_headers(header)
        writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for raw in reader:
            item = {
                columns[i]: ("" if i >= len(raw) or raw[i] is None else str(raw[i]).strip())
                for i in range(len(columns))
            }
            if not any(item.values()):
                continue
            writer.writerow(item)
            row_count += 1
            if len(sample) < sample_limit:
                sample.append(item)
    return columns, sample, row_count, "csv", "csv"


def _materialize_excel(path: Path, dest: Path, sample_limit: int) -> tuple[list[str], list[dict], int, str, str]:
    from openpyxl import load_workbook

    dest.parent.mkdir(parents=True, exist_ok=True)
    book = load_workbook(path, read_only=True, data_only=True)
    sheet = book.active
    sample: list[dict[str, str]] = []
    row_count = 0
    columns: list[str] = []
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = None
        for idx, row in enumerate(sheet.iter_rows(values_only=True)):
            values = list(row)
            if idx == 0:
                columns = _unique_headers(values)
                writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                continue
            assert writer is not None
            item = {
                columns[i]: ("" if i >= len(values) or values[i] is None else str(values[i]).strip())
                for i in range(len(columns))
            }
            if not any(item.values()):
                continue
            writer.writerow(item)
            row_count += 1
            if len(sample) < sample_limit:
                sample.append(item)
    book.close()
    return columns, sample, row_count, sheet.title, "excel"


def _build_column_remap(
    original_columns: list[str], analysis: dict[str, Any]
) -> tuple[list[str], dict[str, str], dict[str, str], list[str]]:
    column_map: dict[str, str] = {}
    dtypes: dict[str, str] = {}
    for col in analysis.get("columns") or []:
        if not isinstance(col, dict):
            continue
        src = str(col.get("name") or "")
        erp = str(col.get("erp_name") or _snake(src))
        if src:
            column_map[src] = erp
            dtypes[erp] = str(col.get("dtype") or "string").lower()

    if not column_map:
        for col in original_columns:
            column_map[col] = _snake(col)
            dtypes[column_map[col]] = "string"

    used: dict[str, int] = {}
    remap: dict[str, str] = {}
    out_columns: list[str] = []
    for src in original_columns:
        name = column_map.get(src, _snake(src))
        if name in used:
            used[name] += 1
            name = f"{name}_{used[name]}"
        else:
            used[name] = 1
        remap[src] = name
        out_columns.append(name)
        if name not in dtypes:
            dtypes[name] = dtypes.get(column_map.get(src, ""), "string")

    key_cols = [k for k in (analysis.get("key_columns") or []) if isinstance(k, str)]
    if not key_cols:
        key_cols = list(out_columns)
    return out_columns, remap, dtypes, key_cols


def _looks_like_id_column(col_name: str, dtype: str) -> bool:
    name = (col_name or "").lower()
    dtype_l = (dtype or "").lower()
    if dtype_l in {"id", "code", "sku"}:
        return True
    tokens = ("_id", " id", "invoice", "code", "sku", "ref", "po_", "order_no", "doc_no")
    return any(t in name for t in tokens) or name.endswith("id") or name in {"id", "uuid", "guid"}


def _sql_normalize(
    src_ident: str,
    dtype: str,
    *,
    col_name: str,
    trim_whitespace: bool = True,
    nullify_placeholders: bool = True,
    normalize_numbers: bool = True,
    standardize_dates: bool = True,
    lowercase_emails: bool = True,
    uppercase_ids: bool = False,
) -> str:
    """Optional whitespace / placeholder / number / date / email / id cleanup."""
    raw = f"COALESCE(CAST({src_ident} AS VARCHAR), '')"
    if trim_whitespace:
        base = f"trim(regexp_replace({raw}, '\\s+', ' ', 'g'))"
    else:
        base = raw

    if nullify_placeholders:
        base = f"""CASE
          WHEN lower(trim({base})) IN ('n/a', 'na', 'null', 'none', '-', '#n/a', 'nil', '.', 'nan') THEN ''
          ELSE {base}
        END"""

    name = (col_name or "").lower()
    dtype_l = (dtype or "string").lower()

    if lowercase_emails and ("email" in name or dtype_l == "email"):
        return f"lower({base})"

    if normalize_numbers and dtype_l in {"number", "currency"}:
        return (
            f"trim(replace(replace(replace(replace({base}, ',', ''), '$', ''), "
            f"'€', ''), '£', ''))"
        )

    if standardize_dates and dtype_l == "date":
        # Prefer ISO; otherwise try common US/EU slash forms.
        return f"""
        COALESCE(
          CAST(TRY_CAST(substr({base}, 1, 10) AS DATE) AS VARCHAR),
          strftime(TRY_STRPTIME({base}, '%m/%d/%Y'), '%Y-%m-%d'),
          strftime(TRY_STRPTIME({base}, '%d/%m/%Y'), '%Y-%m-%d'),
          strftime(TRY_STRPTIME({base}, '%Y/%m/%d'), '%Y-%m-%d'),
          strftime(TRY_STRPTIME({base}, '%m-%d-%Y'), '%Y-%m-%d'),
          strftime(TRY_STRPTIME({base}, '%d-%m-%Y'), '%Y-%m-%d'),
          {base}
        )
        """.strip()

    if uppercase_ids and _looks_like_id_column(col_name, dtype):
        return f"upper({base})"

    return base


def stream_clean(
    *,
    raw_path: Path,
    clean_path: Path,
    analysis: dict[str, Any],
    drop_blank_rows: bool = True,
    drop_blank_keys: bool = True,
    dedupe_keys: bool = True,
    drop_exact_duplicates: bool = False,
    rename_erp: bool = True,
    trim_whitespace: bool = True,
    nullify_placeholders: bool = True,
    normalize_numbers: bool = True,
    standardize_dates: bool = True,
    lowercase_emails: bool = True,
    uppercase_ids: bool = False,
) -> dict[str, Any]:
    """Clean/rename/dedupe via DuckDB; write clean.csv; return sample + stats only.

    Human-in-the-loop options control which steps run. Auto mode uses recommended defaults.
    """
    options = {
        "drop_blank_rows": drop_blank_rows,
        "drop_blank_keys": drop_blank_keys,
        "dedupe_keys": dedupe_keys,
        "drop_exact_duplicates": drop_exact_duplicates,
        "rename_erp": rename_erp,
        "trim_whitespace": trim_whitespace,
        "nullify_placeholders": nullify_placeholders,
        "normalize_numbers": normalize_numbers,
        "standardize_dates": standardize_dates,
        "lowercase_emails": lowercase_emails,
        "uppercase_ids": uppercase_ids,
    }
    if not raw_path.is_file():
        raise ValueError("Raw table missing.")

    with duck_connection() as con:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE raw AS
            SELECT * FROM read_csv_auto(
                {quote_path(raw_path)},
                header=true,
                all_varchar=true,
                sample_size=-1
            )
            """
        )
        original_columns = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
        empty_stats = {
            "input_rows": 0,
            "blank_rows_removed": 0,
            "blank_key_rows_removed": 0,
            "duplicates_removed": 0,
            "exact_duplicates_removed": 0,
            "output_rows": 0,
            "rows_before_dedupe": 0,
            "engine": "duckdb",
        }
        if not original_columns:
            clean_path.parent.mkdir(parents=True, exist_ok=True)
            write_dicts_csv(clean_path, [], [])
            return {
                "columns": [],
                "row_count": 0,
                "sample_rows": [],
                "disk_backed": True,
                "clean_table": clean_path.name,
                "dtypes": {},
                "key_columns": [],
                "column_map": {},
                "options": options,
                "stats": empty_stats,
            }

        if rename_erp:
            out_columns, remap, dtypes, key_cols = _build_column_remap(original_columns, analysis)
        else:
            out_columns = list(original_columns)
            remap = {c: c for c in original_columns}
            # Infer light dtypes from analysis when headers still match.
            dtypes = {c: "string" for c in original_columns}
            for col in analysis.get("columns") or []:
                if not isinstance(col, dict):
                    continue
                src = str(col.get("name") or "")
                erp = str(col.get("erp_name") or src)
                dtype = str(col.get("dtype") or "string")
                if src in dtypes:
                    dtypes[src] = dtype
                if erp in dtypes:
                    dtypes[erp] = dtype
            analyzed_keys = [str(k) for k in (analysis.get("key_columns") or []) if k]
            key_cols = [k for k in analyzed_keys if k in out_columns] or list(out_columns[:1])

        select_parts = []
        for src in original_columns:
            dst = remap[src]
            dtype = dtypes.get(dst, "string")
            select_parts.append(
                f"{_sql_normalize(quote_ident(src), dtype, col_name=dst, trim_whitespace=trim_whitespace, nullify_placeholders=nullify_placeholders, normalize_numbers=normalize_numbers, standardize_dates=standardize_dates, lowercase_emails=lowercase_emails, uppercase_ids=uppercase_ids)} AS {quote_ident(dst)}"
            )

        non_blank = " OR ".join(f"{quote_ident(c)} <> ''" for c in out_columns) or "TRUE"
        key_present = [k for k in key_cols if k in out_columns] or list(out_columns)
        partition = ", ".join(quote_ident(k) for k in key_present)
        key_filled = " AND ".join(
            f"({quote_ident(k)} IS NOT NULL AND trim(CAST({quote_ident(k)} AS VARCHAR)) <> '')"
            for k in key_present
        ) or "TRUE"

        con.execute(
            f"""
            CREATE OR REPLACE TABLE renamed AS
            SELECT {", ".join(select_parts)}
            FROM raw
            """
        )
        rows_in = int(con.execute("SELECT COUNT(*) FROM renamed").fetchone()[0])

        working = "renamed"
        blank_dropped = 0
        blank_key_dropped = 0
        exact_dup_dropped = 0

        if drop_blank_rows:
            con.execute(
                f"""
                CREATE OR REPLACE TABLE nonblank AS
                SELECT * FROM {working}
                WHERE {non_blank}
                """
            )
            rows_after = int(con.execute("SELECT COUNT(*) FROM nonblank").fetchone()[0])
            blank_dropped = rows_in - rows_after
            working = "nonblank"
        else:
            con.execute(f"CREATE OR REPLACE TABLE nonblank AS SELECT * FROM {working}")
            working = "nonblank"

        rows_after_blank = int(con.execute(f"SELECT COUNT(*) FROM {working}").fetchone()[0])

        if drop_blank_keys:
            con.execute(
                f"""
                CREATE OR REPLACE TABLE keyed AS
                SELECT * FROM {working}
                WHERE {key_filled}
                """
            )
            rows_keyed = int(con.execute("SELECT COUNT(*) FROM keyed").fetchone()[0])
            blank_key_dropped = rows_after_blank - rows_keyed
            working = "keyed"
        else:
            con.execute(f"CREATE OR REPLACE TABLE keyed AS SELECT * FROM {working}")
            working = "keyed"

        rows_nonblank = int(con.execute(f"SELECT COUNT(*) FROM {working}").fetchone()[0])

        if dedupe_keys:
            con.execute(
                f"""
                CREATE OR REPLACE TABLE cleaned AS
                SELECT * FROM (
                    SELECT *,
                           row_number() OVER (PARTITION BY {partition} ORDER BY 1) AS _rn
                    FROM {working}
                ) t
                WHERE _rn = 1
                """
            )
            keep = ", ".join(quote_ident(c) for c in out_columns)
            con.execute(f"CREATE OR REPLACE TABLE cleaned_keys AS SELECT {keep} FROM cleaned")
            working = "cleaned_keys"
        else:
            keep = ", ".join(quote_ident(c) for c in out_columns)
            con.execute(f"CREATE OR REPLACE TABLE cleaned_keys AS SELECT {keep} FROM {working}")
            working = "cleaned_keys"

        rows_after_key_dedupe = int(con.execute(f"SELECT COUNT(*) FROM {working}").fetchone()[0])
        duplicates_removed = rows_nonblank - rows_after_key_dedupe

        if drop_exact_duplicates:
            all_cols = ", ".join(quote_ident(c) for c in out_columns)
            con.execute(
                f"""
                CREATE OR REPLACE TABLE cleaned_out AS
                SELECT {all_cols} FROM (
                    SELECT *,
                           row_number() OVER (PARTITION BY {all_cols} ORDER BY 1) AS _rn
                    FROM {working}
                ) t
                WHERE _rn = 1
                """
            )
            rows_out = int(con.execute("SELECT COUNT(*) FROM cleaned_out").fetchone()[0])
            exact_dup_dropped = rows_after_key_dedupe - rows_out
        else:
            keep = ", ".join(quote_ident(c) for c in out_columns)
            con.execute(f"CREATE OR REPLACE TABLE cleaned_out AS SELECT {keep} FROM {working}")
            rows_out = int(con.execute("SELECT COUNT(*) FROM cleaned_out").fetchone()[0])

        clean_path.parent.mkdir(parents=True, exist_ok=True)
        if clean_path.exists():
            clean_path.unlink()
        con.execute(
            f"""
            COPY cleaned_out TO {quote_path(clean_path)} (HEADER, DELIMITER ',')
            """
        )

        sample_limit = idp_sample_rows()
        sample_rows_raw = con.execute(
            f"SELECT * FROM cleaned_out LIMIT {int(sample_limit)}"
        ).fetchall()
        sample: list[dict[str, str]] = []
        for tup in sample_rows_raw:
            sample.append({out_columns[i]: ("" if v is None else str(v)) for i, v in enumerate(tup)})

    return {
        "columns": out_columns,
        "row_count": rows_out,
        "sample_rows": sample,
        "disk_backed": True,
        "clean_table": clean_path.name,
        "dtypes": dtypes,
        "key_columns": key_cols,
        "column_map": remap,
        "options": options,
        "stats": {
            "input_rows": rows_in,
            "blank_rows_removed": blank_dropped,
            "blank_key_rows_removed": blank_key_dropped,
            "duplicates_removed": duplicates_removed,
            "exact_duplicates_removed": exact_dup_dropped,
            "output_rows": rows_out,
            "rows_before_dedupe": rows_nonblank,
            "engine": "duckdb",
        },
    }


def fetch_clean_row(clean_path: Path, row_index: int) -> dict[str, Any] | None:
    """Return one cleaned row by 0-based index from disk (not the full file)."""
    if row_index < 0:
        raise ValueError("row_index must be >= 0")
    if not clean_path.is_file():
        return None
    with duck_connection() as con:
        try:
            total = int(
                con.execute(
                    f"""
                    SELECT COUNT(*) FROM read_csv_auto(
                        {quote_path(clean_path)},
                        HEADER=true,
                        SAMPLE_SIZE=-1,
                        IGNORE_ERRORS=true,
                        ALL_VARCHAR=true
                    )
                    """
                ).fetchone()[0]
            )
        except Exception:  # noqa: BLE001
            return None
        if row_index >= total:
            return None
        relation = con.execute(
            f"""
            SELECT * FROM read_csv_auto(
                {quote_path(clean_path)},
                HEADER=true,
                SAMPLE_SIZE=-1,
                IGNORE_ERRORS=true,
                ALL_VARCHAR=true
            )
            LIMIT 1 OFFSET {int(row_index)}
            """
        )
        columns = [d[0] for d in relation.description]
        tup = relation.fetchone()
        if not tup:
            return None
        row = {columns[i]: ("" if v is None else str(v)) for i, v in enumerate(tup)}
        return {"columns": columns, "row": row, "row_index": row_index, "row_count": total}


def stream_validate(clean_path: Path, cleaned_meta: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """DuckDB validation with a hard cap of 200 exceptions for the review desk."""
    columns = list(cleaned_meta.get("columns") or [])
    dtypes: dict[str, str] = dict(cleaned_meta.get("dtypes") or {})
    key_columns: list[str] = list(cleaned_meta.get("key_columns") or [])
    issues: list[dict[str, Any]] = []
    max_exceptions = 200
    rows_checked = 0

    def add(
        code: str,
        severity: str,
        message: str,
        row_index: int | None,
        field_name: str | None,
        value: Any,
    ) -> bool:
        if len(issues) >= max_exceptions:
            return True
        issues.append(
            {
                "id": str(uuid.uuid4()),
                "code": code,
                "severity": severity,
                "message": message,
                "row_index": row_index,
                "field_name": field_name,
                "value": value,
                "status": "pending",
            }
        )
        return len(issues) >= max_exceptions

    if not clean_path.is_file() or not columns:
        add("NO_COLUMNS" if not columns else "EMPTY_DATASET", "high",
            "No columns detected for ERP export." if not columns else "No data rows remain after cleaning.",
            None, None, None)
        return _validation_result(issues, rows_checked, columns, key_columns, analysis)

    with duck_connection() as con:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE clean AS
            SELECT * FROM read_csv_auto(
                {quote_path(clean_path)},
                header=true,
                all_varchar=true,
                sample_size=-1
            )
            """
        )
        rows_checked = int(con.execute("SELECT COUNT(*) FROM clean").fetchone()[0])
        if rows_checked == 0:
            add("EMPTY_DATASET", "high", "No data rows remain after cleaning.", None, None, None)
            return _validation_result(issues, rows_checked, columns, key_columns, analysis)

        for key in key_columns:
            if key not in columns:
                if add("MISSING_KEY_COLUMN", "high", f"Key column '{key}' is not present.", None, key, None):
                    return _validation_result(issues, rows_checked, columns, key_columns, analysis)
                continue
            remaining = max_exceptions - len(issues)
            if remaining <= 0:
                break
            # Number the full clean table first, then filter — otherwise rn is only among matches.
            q = f"""
                WITH numbered AS (
                    SELECT
                        row_number() OVER () AS rn,
                        {quote_ident(key)} AS v
                    FROM clean
                )
                SELECT rn, v
                FROM numbered
                WHERE v IS NULL OR trim(CAST(v AS VARCHAR)) = ''
                LIMIT {int(remaining)}
            """
            for rn, value in con.execute(q).fetchall():
                if add(
                    "MISSING_KEY_VALUE",
                    "high",
                    f"Key column '{key}' is blank.",
                    int(rn) - 1,
                    key,
                    value,
                ):
                    return _validation_result(issues, rows_checked, columns, key_columns, analysis)

        for col in columns:
            dtype = (dtypes.get(col) or "string").lower()
            remaining = max_exceptions - len(issues)
            if remaining <= 0:
                break
            if dtype in {"number", "currency"}:
                q = f"""
                    WITH numbered AS (
                        SELECT
                            row_number() OVER () AS rn,
                            {quote_ident(col)} AS v
                        FROM clean
                    )
                    SELECT rn, v
                    FROM numbered
                    WHERE v IS NOT NULL
                      AND trim(CAST(v AS VARCHAR)) <> ''
                      AND TRY_CAST(replace(CAST(v AS VARCHAR), ',', '') AS DOUBLE) IS NULL
                    LIMIT {int(remaining)}
                """
                for rn, value in con.execute(q).fetchall():
                    if add(
                        "INVALID_NUMBER",
                        "medium",
                        f"Expected {dtype} in '{col}'.",
                        int(rn) - 1,
                        col,
                        value,
                    ):
                        return _validation_result(issues, rows_checked, columns, key_columns, analysis)
            elif dtype == "date":
                q = f"""
                    WITH numbered AS (
                        SELECT
                            row_number() OVER () AS rn,
                            {quote_ident(col)} AS v
                        FROM clean
                    )
                    SELECT rn, v
                    FROM numbered
                    WHERE v IS NOT NULL
                      AND trim(CAST(v AS VARCHAR)) <> ''
                      AND TRY_CAST(substr(trim(CAST(v AS VARCHAR)), 1, 10) AS DATE) IS NULL
                    LIMIT {int(remaining)}
                """
                for rn, value in con.execute(q).fetchall():
                    if add(
                        "INVALID_DATE",
                        "medium",
                        f"Expected ISO date in '{col}'.",
                        int(rn) - 1,
                        col,
                        value,
                    ):
                        return _validation_result(issues, rows_checked, columns, key_columns, analysis)

    return _validation_result(issues, rows_checked, columns, key_columns, analysis)


def _validation_result(
    issues: list[dict[str, Any]],
    rows_checked: int,
    columns: list[str],
    key_columns: list[str],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    for issue in analysis.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if len(issues) >= 200:
            break
        issues.append(
            {
                "id": str(uuid.uuid4()),
                "code": str(issue.get("code") or "AI_ISSUE"),
                "severity": "low" if issue.get("code") == "AI_FALLBACK" else "medium",
                "message": str(issue.get("message") or "AI flagged an issue."),
                "row_index": issue.get("row_hint"),
                "field_name": None,
                "value": None,
                "status": "pending",
            }
        )

    return {
        "ok": len(issues) == 0,
        "exception_count": len(issues),
        "truncated": 0,
        "exceptions": issues[:200],
        "summary": {
            "rows_checked": rows_checked,
            "columns_checked": len(columns),
            "key_columns": key_columns,
            "engine": "duckdb",
        },
    }
