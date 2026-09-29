import hashlib
import sqlite3

import pytest

import app.audit_log as audit_log
from tests.conftest import SENIOR, auth, login, samples


def test_audit_log_is_append_only_and_records_the_review_path(client):
    test_client, data = client
    token = login(test_client, SENIOR)
    headers = auth(token)
    created = test_client.post(
        "/engagements",
        headers=headers,
        json={"name": "Trail", "assign_auditors": False},
    )
    engagement_id = created.json()["id"]
    for name in ("purchase_order.pdf", "invoice.pdf", "payment.pdf", "approval_policy.pdf"):
        with (samples() / name).open("rb") as handle:
            response = test_client.post(
                f"/engagements/{engagement_id}/documents",
                headers=headers,
                files={"file": (name, handle, "application/pdf")},
            )
        assert response.status_code == 200, response.text

    assert test_client.get(f"/engagements/{engagement_id}/evidence", headers=headers).status_code == 200
    assert (
        test_client.post(
            f"/engagements/{engagement_id}/confirm-scope",
            headers=headers,
            json={"audit_type": "procurement_financial"},
        ).status_code
        == 200
    )
    analyzed = test_client.post(f"/engagements/{engagement_id}/analyze", headers=headers)
    finding_id = next(item["id"] for item in analyzed.json()["findings"] if item["rule_id"] == "AMOUNT_MISMATCH")
    assert (
        test_client.post(
            f"/findings/{finding_id}/review",
            headers=headers,
            json={"action": "approve"},
        ).status_code
        == 200
    )

    events = test_client.get("/audit-events", headers=headers)
    assert events.status_code == 200, events.text
    rows = events.json()
    assert rows[0]["id"] >= rows[-1]["id"]
    actions = {row["action"] for row in rows}
    assert "EVIDENCE_VIEWED" in actions
    assert "EXTRACTION_COMPLETED" in actions
    assert "ANALYSIS_STARTED" in actions
    assert "ANALYSIS_COMPLETED" in actions
    assert "FINDING_APPROVED" in actions
    approved = next(row for row in rows if row["action"] == "FINDING_APPROVED")
    assert approved["payload"]["review_status"] == "approved"
    assert approved["payload"]["rule_id"] == "AMOUNT_MISMATCH"

    chronological = sorted(rows, key=lambda row: row["id"])
    previous = "GENESIS"
    for row in chronological:
        assert row["prev_hash"] == previous
        digest = hashlib.sha256(f"{row['prev_hash']}{row['payload_hash']}".encode("utf-8")).hexdigest()
        assert row["chain_hash"] == digest
        previous = row["chain_hash"]

    names = [name for name in dir(audit_log) if "delete" in name.lower() or "update" in name.lower()]
    assert names == []

    assert test_client.delete("/audit-events").status_code == 405

    connection = sqlite3.connect(data / "audit.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM audit_events")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE audit_events SET action = 'tampered'")
    finally:
        connection.close()
