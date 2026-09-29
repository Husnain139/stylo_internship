from fastapi.testclient import TestClient

from tests.conftest import JUNIOR, SENIOR, auth, login, samples


def _pack(test_client: TestClient) -> tuple[str, str]:
    token = login(test_client, SENIOR)
    created = test_client.post(
        "/engagements",
        headers=auth(token),
        json={"name": "Synthetic procurement", "assign_auditors": False},
    )
    assert created.status_code == 200, created.text
    engagement_id = created.json()["id"]
    for path in (
        samples() / "purchase_order.pdf",
        samples() / "invoice.pdf",
        samples() / "payment.pdf",
        samples() / "approval_policy.pdf",
    ):
        with path.open("rb") as handle:
            uploaded = test_client.post(
                f"/engagements/{engagement_id}/documents",
                headers=auth(token),
                files={"file": (path.name, handle, "application/pdf")},
            )
        assert uploaded.status_code == 200, uploaded.text
    return token, engagement_id


def test_seeded_amount_mismatch_is_computed_not_guessed(client):
    test_client, _data = client
    token, engagement_id = _pack(test_client)
    headers = auth(token)

    evidence = test_client.get(f"/engagements/{engagement_id}/evidence", headers=headers)
    assert evidence.status_code == 200, evidence.text
    documents = evidence.json()["documents"]
    invoice = next(item for item in documents if item["document_class"] == "invoice")
    amount = next(field for field in invoice["fields"] if field["field_name"] == "amount")
    approval = next(field for field in invoice["fields"] if field["field_name"] == "approval_status")
    description = next(field for field in invoice["fields"] if field["field_name"] == "description")
    assert amount["value"] == "PKR 250,000"
    assert amount["page"] == 2
    assert amount["validation_status"] == "validated"
    assert approval["validation_status"] == "not_found"
    assert description["validation_status"] == "unverified"
    assert description["source"] == "notable"

    denied = test_client.post(
        f"/engagements/{engagement_id}/analyze",
        headers=headers,
    )
    assert denied.status_code == 409

    confirmed = test_client.post(
        f"/engagements/{engagement_id}/confirm-scope",
        headers=headers,
        json={"audit_type": "procurement_financial"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["scope_status"] == "confirmed"

    junior = login(test_client, JUNIOR)
    blocked = test_client.post(
        f"/engagements/{engagement_id}/confirm-scope",
        headers=auth(junior),
        json={},
    )
    assert blocked.status_code == 403

    analyzed = test_client.post(f"/engagements/{engagement_id}/analyze", headers=headers)
    assert analyzed.status_code == 200, analyzed.text
    mismatch = next(item for item in analyzed.json()["findings"] if item["rule_id"] == "AMOUNT_MISMATCH")
    assert mismatch["delta_amount"] == 50000
    assert mismatch["currency"] == "PKR"
    assert mismatch["risk_band"] == "high"
    assert mismatch["narrative_status"] == "exception — investigation required"
    assert "fraud" not in mismatch["explanation"].lower()
    assert "50,000" in mismatch["explanation"]
    assert mismatch["detail"]["invoice_amount"] == 250000
    assert mismatch["detail"]["po_amount"] == 200000
    assert len(mismatch["evidence"]) >= 2
    assert {item["field_name"] for item in mismatch["evidence"]} >= {"amount"}

    missing = next(item for item in analyzed.json()["findings"] if item["rule_id"] == "MISSING_APPROVAL")
    assert missing["risk_band"] == "high"
    assert missing["detail"]["spending_limit"] == 200000
