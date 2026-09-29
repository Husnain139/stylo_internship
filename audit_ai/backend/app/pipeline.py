"""Classify, extract, and reconcile procurement documents.

Money and matches are computed here. A model may only phrase the finding.
"""

from __future__ import annotations

import re
from collections import defaultdict

REQUIRED_CLASSES = ("purchase_order", "invoice", "payment", "policy")
NARRATIVE = "exception — investigation required"

SCHEMAS: dict[str, list[tuple[str, str, str]]] = {
    "invoice": [
        ("invoice_id", r"Invoice ID:\s*([A-Za-z0-9-]+)", "text"),
        ("vendor", r"Vendor:\s*(.+)", "text"),
        ("invoice_date", r"Invoice date:\s*(.+)", "date"),
        ("amount", r"Amount:\s*(PKR\s*[\d,]+)", "money"),
        ("tax", r"Tax:\s*(PKR\s*[\d,]+)", "money"),
        ("po_reference", r"PO Reference:\s*([A-Za-z0-9-]+)", "text"),
        ("approval_status", r"Approval status:\s*(.+)", "approval"),
    ],
    "purchase_order": [
        ("po_number", r"PO Number:\s*([A-Za-z0-9-]+)", "text"),
        ("vendor", r"Vendor:\s*(.+)", "text"),
        ("po_date", r"(?m)^Date:\s*(.+)", "date"),
        ("amount", r"Amount:\s*(PKR\s*[\d,]+)", "money"),
        ("approved_by", r"Approved by:\s*(.+)", "text"),
    ],
    "payment": [
        ("payment_id", r"Payment ID:\s*([A-Za-z0-9-]+)", "text"),
        ("vendor", r"Vendor:\s*(.+)", "text"),
        ("payment_date", r"(?m)^Date:\s*(.+)", "date"),
        ("amount", r"Amount:\s*(PKR\s*[\d,]+)", "money"),
        ("reference", r"Reference:\s*([A-Za-z0-9-]+)", "text"),
    ],
    "policy": [
        ("policy_name", r"Policy name:\s*(.+)", "text"),
        ("spending_limit", r"Spending limit:\s*(PKR\s*[\d,]+)", "money"),
        ("approval_required_above", r"Approval required above:\s*(PKR\s*[\d,]+)", "money"),
    ],
}


def classify_text(text: str) -> dict:
    upper = text.upper()
    if "PURCHASE ORDER" in upper:
        kind = "purchase_order"
    elif "INVOICE" in upper:
        kind = "invoice"
    elif "PAYMENT RECORD" in upper or "PAYMENT ID:" in upper:
        kind = "payment"
    elif "APPROVAL POLICY" in upper or "POLICY NAME:" in upper:
        kind = "policy"
    else:
        kind = "unknown"
    if kind == "unknown":
        return {"document_class": kind, "confidence": 0.2, "reasons": ["No known procurement heading was found"]}
    return {
        "document_class": kind,
        "confidence": 0.93,
        "reasons": [f"Matched a {kind.replace('_', ' ')} heading in the document text"],
    }


def parse_pkr(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    return int(digits)


def _validate(kind: str, value: str | None) -> str:
    if value is None or not str(value).strip():
        return "not_found"
    text = str(value).strip()
    if kind == "approval" and "not found" in text.lower():
        return "not_found"
    if kind == "money":
        return "validated" if parse_pkr(text) is not None else "failed"
    if kind == "date":
        return "validated" if re.search(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", text) else "failed"
    return "validated"


def _search(pages: list[tuple[int, str]], pattern: str) -> tuple[int | None, str | None]:
    regex = re.compile(pattern, re.IGNORECASE)
    for number, text in pages:
        match = regex.search(text)
        if match:
            return number, match.group(1).strip()
    return None, None


def extract_fields(document_class: str, pages: list[tuple[int, str]]) -> list[dict]:
    schema = SCHEMAS.get(document_class, [])
    fields: list[dict] = []
    for name, pattern, kind in schema:
        page, value = _search(pages, pattern)
        status = _validate(kind, value)
        fields.append(
            {
                "field_name": name,
                "value": value,
                "page": page,
                "confidence": 0.93 if value else 0.0,
                "validation_status": status,
                "source": "schema",
            }
        )
    full = "\n".join(text for _, text in pages)
    description = re.search(r"Description:\s*(.+)", full, re.IGNORECASE)
    if description and document_class in {"invoice", "purchase_order"}:
        page, _ = _search(pages, r"Description:\s*(.+)")
        fields.append(
            {
                "field_name": "description",
                "value": description.group(1).strip(),
                "page": page,
                "confidence": 0.4,
                "validation_status": "unverified",
                "source": "notable",
            }
        )
    return fields


def propose_scope(classes: list[str]) -> dict:
    present = sorted({item for item in classes if item and item != "unknown"})
    missing = [name for name in REQUIRED_CLASSES if name not in present]
    reasons = [f"Classified document as {name.replace('_', ' ')}" for name in present]
    if not present:
        confidence = 0.0
        proposed = "unknown"
        reasons = ["No procurement documents classified yet"]
    elif missing:
        confidence = 0.62
        proposed = "procurement_financial"
    else:
        confidence = 0.9
        proposed = "procurement_financial"
    return {
        "proposed_type": proposed,
        "proposed_confidence": confidence,
        "proposed_reasons": reasons,
        "missing_evidence": missing,
    }


def _records(documents: list[dict]) -> list[dict]:
    records = []
    for document in documents:
        schema_fields = {
            field["field_name"]: field
            for field in document["fields"]
            if field["source"] == "schema"
        }
        records.append({"document": document, "fields": schema_fields})
    return records


def _value(record: dict, name: str) -> str | None:
    field = record["fields"].get(name)
    if not field:
        return None
    return field.get("value")


def _field_id(record: dict, name: str) -> str | None:
    field = record["fields"].get(name)
    if not field:
        return None
    return field.get("id")


def draft_explanation(finding: dict) -> str:
    rule = finding["rule_id"]
    detail = finding.get("detail") or {}
    if rule == "AMOUNT_MISMATCH":
        delta = finding.get("delta_amount") or 0
        return (
            f"Invoice amount differs from the matched purchase order by PKR {delta:,}. "
            "Status: exception requiring investigation. "
            "No amendment document was found in this engagement."
        )
    if rule == "MISSING_APPROVAL":
        return (
            "Invoice amount exceeds the policy spending limit and no approval was found "
            "in the provided records. Confirmation is required."
        )
    if rule == "DUPLICATE_PAYMENT":
        return (
            "Two or more payments share the same vendor, amount, and date. "
            "They are flagged as an exception requiring investigation."
        )
    if rule == "UNMATCHED_INVOICE":
        return (
            "No purchase order in the provided records matches this invoice. "
            "The link is not found, so the invoice cannot be tied to an agreed price."
        )
    return f"Rule {rule} produced an exception requiring investigation. Detail: {detail}."


def _finding(
    *,
    rule_id: str,
    title: str,
    delta: int | None,
    risk: str,
    evidence_ids: list[str],
    detail: dict,
) -> dict:
    body = {
        "rule_id": rule_id,
        "title": title,
        "narrative_status": NARRATIVE,
        "delta_amount": delta,
        "currency": "PKR" if delta is not None or rule_id != "DUPLICATE_PAYMENT" else "PKR",
        "risk_band": risk,
        "evidence_ids": [item for item in evidence_ids if item],
        "detail": detail,
    }
    body["currency"] = "PKR"
    body["explanation"] = draft_explanation(body)
    return body


def analyze_documents(documents: list[dict]) -> list[dict]:
    """documents items: {id, filename, document_class, fields: [{id, field_name, value, source}]}"""
    grouped = _records(documents)
    invoices = [item for item in grouped if item["document"]["document_class"] == "invoice"]
    orders = [item for item in grouped if item["document"]["document_class"] == "purchase_order"]
    payments = [item for item in grouped if item["document"]["document_class"] == "payment"]
    policies = [item for item in grouped if item["document"]["document_class"] == "policy"]
    findings: list[dict] = []

    limit = None
    if policies:
        limit = parse_pkr(_value(policies[0], "spending_limit"))

    for invoice in invoices:
        po_number = _value(invoice, "po_reference")
        vendor = (_value(invoice, "vendor") or "").strip().lower()
        match = next((po for po in orders if _value(po, "po_number") == po_number), None)
        if match is None and vendor:
            match = next((po for po in orders if (_value(po, "vendor") or "").strip().lower() == vendor), None)
        invoice_amount = parse_pkr(_value(invoice, "amount"))
        if match is None:
            findings.append(
                _finding(
                    rule_id="UNMATCHED_INVOICE",
                    title="Invoice has no matching purchase order in the provided records",
                    delta=None,
                    risk="medium",
                    evidence_ids=[_field_id(invoice, "invoice_id"), _field_id(invoice, "po_reference")],
                    detail={"invoice_id": _value(invoice, "invoice_id"), "vendor": _value(invoice, "vendor")},
                )
            )
        else:
            po_amount = parse_pkr(_value(match, "amount"))
            if invoice_amount is not None and po_amount is not None and invoice_amount != po_amount:
                delta = invoice_amount - po_amount
                risk = "high" if abs(delta) >= 50_000 else "medium"
                findings.append(
                    _finding(
                        rule_id="AMOUNT_MISMATCH",
                        title="Invoice amount differs from purchase order",
                        delta=delta,
                        risk=risk,
                        evidence_ids=[_field_id(invoice, "amount"), _field_id(match, "amount")],
                        detail={
                            "invoice_id": _value(invoice, "invoice_id"),
                            "po_number": _value(match, "po_number"),
                            "vendor": _value(invoice, "vendor"),
                            "invoice_amount": invoice_amount,
                            "po_amount": po_amount,
                        },
                    )
                )
        approval = _value(invoice, "approval_status")
        approval_missing = approval is None or "not found" in approval.lower()
        if limit is not None and invoice_amount is not None and invoice_amount > limit and approval_missing:
            findings.append(
                _finding(
                    rule_id="MISSING_APPROVAL",
                    title="Approval not found for amount above policy limit",
                    delta=invoice_amount - limit,
                    risk="high",
                    evidence_ids=[
                        _field_id(invoice, "amount"),
                        _field_id(invoice, "approval_status"),
                        _field_id(policies[0], "spending_limit"),
                    ],
                    detail={
                        "invoice_amount": invoice_amount,
                        "spending_limit": limit,
                        "approval_status": approval or "not found",
                    },
                )
            )

    groups: dict[tuple, list] = defaultdict(list)
    for payment in payments:
        amount = parse_pkr(_value(payment, "amount"))
        key = ((_value(payment, "vendor") or "").strip().lower(), amount, (_value(payment, "payment_date") or "").strip())
        if amount is None:
            continue
        groups[key].append(payment)
    for key, items in groups.items():
        if len(items) < 2:
            continue
        vendor, amount, paid_on = key
        findings.append(
            _finding(
                rule_id="DUPLICATE_PAYMENT",
                title="Duplicate payment candidate",
                delta=None,
                risk="medium",
                evidence_ids=[_field_id(item, "payment_id") for item in items],
                detail={"vendor": vendor, "amount": amount, "payment_date": paid_on, "count": len(items)},
            )
        )
    return findings
