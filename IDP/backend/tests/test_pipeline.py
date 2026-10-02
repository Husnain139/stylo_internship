"""Unit tests for clean + validate (no network)."""

from __future__ import annotations

from app.clean import clean_and_standardize
from app.validate import validate_dataset


def test_clean_removes_blanks_and_duplicates():
    rows = [
        {"Vendor": "Acme", "Amount": "100"},
        {"Vendor": "", "Amount": ""},
        {"Vendor": "Acme", "Amount": "100"},
        {"Vendor": "Beta", "Amount": "50.5"},
    ]
    analysis = {
        "columns": [
            {"name": "Vendor", "erp_name": "vendor", "dtype": "string"},
            {"name": "Amount", "erp_name": "amount", "dtype": "currency"},
        ],
        "key_columns": ["vendor", "amount"],
    }
    cleaned = clean_and_standardize(rows, analysis)
    assert cleaned["stats"]["blank_rows_removed"] == 1
    assert cleaned["stats"]["duplicates_removed"] == 1
    assert cleaned["row_count"] == 2
    assert cleaned["rows"][0]["vendor"] == "Acme"
    assert cleaned["rows"][0]["amount"] == 100


def test_validate_flags_missing_key():
    cleaned = {
        "columns": ["vendor", "amount"],
        "rows": [{"vendor": "", "amount": 10}],
        "dtypes": {"vendor": "string", "amount": "currency"},
        "key_columns": ["vendor"],
    }
    result = validate_dataset(cleaned, {"issues": []})
    codes = {e["code"] for e in result["exceptions"]}
    assert "MISSING_KEY_VALUE" in codes
