"""Smoke: DuckDB clean/validate + large CSV export policy + docx/pdf ingest."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("IDP_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))

from app.config import xlsx_max_rows
from app.export import export_from_clean_csv
from app.stream import materialize_upload, stream_clean, stream_validate, tables_dir, write_dicts_csv


def main() -> None:
    td = tables_dir()
    job = "smoke-duck"
    raw = td / f"{job}.raw.csv"
    clean = td / f"{job}.clean.csv"

    rows = [
        {"Vendor": "Acme", "Amount": "$100"},
        {"Vendor": "", "Amount": ""},
        {"Vendor": "Acme", "Amount": "$100"},
        {"Vendor": "Beta", "Amount": "50.5"},
    ]
    write_dicts_csv(raw, ["Vendor", "Amount"], rows)
    analysis = {
        "columns": [
            {"name": "Vendor", "erp_name": "vendor", "dtype": "string"},
            {"name": "Amount", "erp_name": "amount", "dtype": "currency"},
        ],
        "key_columns": ["vendor", "amount"],
    }
    cleaned = stream_clean(raw_path=raw, clean_path=clean, analysis=analysis)
    print("SMALL clean", cleaned["stats"], "rows", cleaned["row_count"])
    assert cleaned["row_count"] == 2
    assert cleaned["stats"]["engine"] == "duckdb"
    val = stream_validate(clean, cleaned, analysis)
    print("SMALL validate", val["exception_count"], val["summary"])

    n = xlsx_max_rows() + 1
    job2 = "smoke-large"
    raw2 = td / f"{job2}.raw.csv"
    clean2 = td / f"{job2}.clean.csv"
    print(f"Writing {n} rows...")
    with raw2.open("w", encoding="utf-8", newline="") as fh:
        fh.write("id,amount\n")
        for i in range(n):
            fh.write(f"{i},{i}.5\n")
    analysis2 = {
        "columns": [
            {"name": "id", "erp_name": "id", "dtype": "string"},
            {"name": "amount", "erp_name": "amount", "dtype": "currency"},
        ],
        "key_columns": ["id"],
    }
    cleaned2 = stream_clean(raw_path=raw2, clean_path=clean2, analysis=analysis2)
    print("LARGE clean", cleaned2["stats"])
    assert cleaned2["row_count"] == n
    data = Path(os.environ["IDP_DATA_DIR"])
    exp = export_from_clean_csv(
        clean2,
        columns=cleaned2["columns"],
        export_dir=data / "exports",
        job_id=job2,
        basename="large.csv",
        row_count=cleaned2["row_count"],
    )
    print("LARGE export", exp["formats"], exp["xlsx_skipped_reason"])
    assert exp["formats"] == ["csv"]
    assert exp["xlsx_skipped_reason"]
    assert not Path(exp["csv_path"]).with_suffix(".xlsx").is_file()

    exp_s = export_from_clean_csv(
        clean,
        columns=cleaned["columns"],
        export_dir=data / "exports",
        job_id=job,
        basename="small.csv",
        row_count=cleaned["row_count"],
    )
    print("SMALL export", exp_s["formats"])
    assert "xlsx" in exp_s["formats"]

    uploads = data / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    from docx import Document

    docx_path = uploads / "smoke.docx"
    d = Document()
    table = d.add_table(rows=3, cols=2)
    table.rows[0].cells[0].text = "Vendor"
    table.rows[0].cells[1].text = "Amount"
    table.rows[1].cells[0].text = "Acme"
    table.rows[1].cells[1].text = "10"
    table.rows[2].cells[0].text = "Beta"
    table.rows[2].cells[1].text = "20"
    d.save(docx_path)
    got = materialize_upload(docx_path, filename="smoke.docx", job_id="smoke-docx")
    print("DOCX materialize", got.get("kind"), got.get("row_count"), got.get("columns"), got.get("needs_vision"))
    assert got["row_count"] >= 2
    assert got["needs_vision"] is False

    # Tiny one-page PDF via pymupdf
    import fitz

    pdf_path = uploads / "smoke.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Vendor Amount\nAcme 10\nBeta 20")
    doc.save(pdf_path)
    doc.close()
    got_pdf = materialize_upload(pdf_path, filename="smoke.pdf", job_id="smoke-pdf")
    print(
        "PDF materialize",
        got_pdf.get("kind"),
        got_pdf.get("row_count"),
        got_pdf.get("needs_vision"),
        got_pdf.get("columns"),
    )
    assert got_pdf.get("kind") == "pdf"

    print("SMOKE OK")


if __name__ == "__main__":
    main()
