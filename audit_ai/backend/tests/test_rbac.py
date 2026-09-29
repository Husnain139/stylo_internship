from tests.conftest import ADMIN, JUNIOR, SENIOR, auth, login, samples


def test_junior_cannot_approve_and_senior_can(client):
    test_client, _data = client
    senior = login(test_client, SENIOR)
    created = test_client.post(
        "/engagements",
        headers=auth(senior),
        json={"name": "Review gate", "assign_auditors": False},
    )
    engagement_id = created.json()["id"]

    junior = login(test_client, JUNIOR)
    hidden = test_client.get(f"/engagements/{engagement_id}", headers=auth(junior))
    assert hidden.status_code == 403

    admin = login(test_client, ADMIN)
    assigned = test_client.post(
        f"/engagements/{engagement_id}/members",
        headers=auth(admin),
        json={"email": JUNIOR},
    )
    assert assigned.status_code == 200, assigned.text
    assert test_client.get(f"/engagements/{engagement_id}", headers=auth(junior)).status_code == 200

    with (samples() / "invoice.pdf").open("rb") as handle:
        uploaded = test_client.post(
            f"/engagements/{engagement_id}/documents",
            headers=auth(senior),
            files={"file": ("invoice.pdf", handle, "application/pdf")},
        )
    assert uploaded.status_code == 200, uploaded.text
    for name in ("purchase_order.pdf", "payment.pdf", "approval_policy.pdf"):
        path = samples() / name
        with path.open("rb") as handle:
            assert (
                test_client.post(
                    f"/engagements/{engagement_id}/documents",
                    headers=auth(senior),
                    files={"file": (name, handle, "application/pdf")},
                ).status_code
                == 200
            )

    assert (
        test_client.post(
            f"/engagements/{engagement_id}/confirm-scope",
            headers=auth(junior),
            json={},
        ).status_code
        == 403
    )
    assert (
        test_client.post(
            f"/engagements/{engagement_id}/confirm-scope",
            headers=auth(senior),
            json={},
        ).status_code
        == 200
    )
    analyzed = test_client.post(f"/engagements/{engagement_id}/analyze", headers=auth(senior))
    assert analyzed.status_code == 200, analyzed.text
    finding_id = next(item["id"] for item in analyzed.json()["findings"] if item["rule_id"] == "AMOUNT_MISMATCH")

    assert (
        test_client.post(
            f"/findings/{finding_id}/review",
            headers=auth(junior),
            json={"action": "approve"},
        ).status_code
        == 403
    )
    assert (
        test_client.post(
            f"/findings/{finding_id}/review",
            headers=auth(admin),
            json={"action": "approve"},
        ).status_code
        == 403
    )
    approved = test_client.post(
        f"/findings/{finding_id}/review",
        headers=auth(senior),
        json={"action": "approve", "note": "Agreed. The exception stands for follow-up."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["review_status"] == "approved"
    assert approved.json()["reviewed_by"] == SENIOR

    exported = test_client.get(f"/engagements/{engagement_id}/export", headers=auth(junior))
    assert exported.status_code == 403
    exported = test_client.get(f"/engagements/{engagement_id}/export", headers=auth(senior))
    assert exported.status_code == 200
    assert b"AMOUNT_MISMATCH" in exported.content
