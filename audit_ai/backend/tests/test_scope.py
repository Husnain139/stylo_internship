from tests.conftest import ADMIN, JUNIOR, SENIOR, auth, login


def test_only_a_senior_can_reject_scope_and_analysis_stays_blocked(client):
    test_client, _data = client
    senior = login(test_client, SENIOR)
    created = test_client.post(
        "/engagements",
        headers=auth(senior),
        json={"name": "Scope gate", "assign_auditors": True},
    )
    engagement_id = created.json()["id"]

    junior = login(test_client, JUNIOR)
    admin = login(test_client, ADMIN)
    blank = test_client.post(
        f"/engagements/{engagement_id}/reject-scope",
        headers=auth(senior),
        json={"note": "   "},
    )
    assert blank.status_code == 400

    for token in (junior, admin):
        denied = test_client.post(
            f"/engagements/{engagement_id}/reject-scope",
            headers=auth(token),
            json={"note": "Not our engagement type"},
        )
        assert denied.status_code == 403

    empty_confirm = test_client.post(
        f"/engagements/{engagement_id}/confirm-scope",
        headers=auth(senior),
        json={},
    )
    assert empty_confirm.status_code == 400

    rejected = test_client.post(
        f"/engagements/{engagement_id}/reject-scope",
        headers=auth(senior),
        json={"note": "File set is not a procurement pack"},
    )
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["scope_status"] == "rejected"
    assert body["scope_rejected_by"] == SENIOR
    assert body["scope_rejection_note"] == "File set is not a procurement pack"

    blocked = test_client.post(f"/engagements/{engagement_id}/analyze", headers=auth(senior))
    assert blocked.status_code == 409

    events = test_client.get("/audit-events", headers=auth(senior))
    assert any(row["action"] == "SCOPE_REJECTED" and row["object_id"] == engagement_id for row in events.json())

    frozen = test_client.post(f"/engagements/{engagement_id}/load-samples", headers=auth(junior))
    assert frozen.status_code == 409

    denied_reopen = test_client.post(f"/engagements/{engagement_id}/reopen-scope", headers=auth(junior))
    assert denied_reopen.status_code == 403

    reopened = test_client.post(f"/engagements/{engagement_id}/reopen-scope", headers=auth(senior))
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["scope_status"] == "proposed"
    assert reopened.json()["scope_rejection_note"] is None

    loaded = test_client.post(f"/engagements/{engagement_id}/load-samples", headers=auth(senior))
    assert loaded.status_code == 200, loaded.text

    confirmed = test_client.post(
        f"/engagements/{engagement_id}/confirm-scope",
        headers=auth(senior),
        json={"audit_type": "procurement_financial"},
    )
    assert confirmed.status_code == 200, confirmed.text
    blocked_after_confirm = test_client.post(f"/engagements/{engagement_id}/load-samples", headers=auth(senior))
    assert blocked_after_confirm.status_code == 409
    reopened_confirmed = test_client.post(f"/engagements/{engagement_id}/reopen-scope", headers=auth(senior))
    assert reopened_confirmed.status_code == 200, reopened_confirmed.text
    assert reopened_confirmed.json()["scope_status"] == "proposed"
    again = test_client.post(f"/engagements/{engagement_id}/load-samples", headers=auth(senior))
    assert again.status_code == 200, again.text
    listed = test_client.get(f"/engagements/{engagement_id}/documents", headers=auth(senior))
    assert len(listed.json()) == 4
