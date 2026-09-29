from tests.conftest import SENIOR, auth, login


def test_sample_packs_cover_core_scenarios(client):
    test_client, _data = client
    token = login(test_client, SENIOR)
    headers = auth(token)

    packs = test_client.get("/sample-packs", headers=headers)
    assert packs.status_code == 200, packs.text
    ids = {item["id"] for item in packs.json()}
    assert {
        "mismatch",
        "clean",
        "missing_po",
        "duplicate_payment",
        "partial",
        "noise",
        "scanned",
        "hybrid",
        "kitchen_sink",
        "multi_vendor",
    } <= ids

    created = test_client.post(
        "/engagements",
        headers=headers,
        json={"name": "Clean pack check", "assign_auditors": False},
    )
    assert created.status_code == 200, created.text
    engagement_id = created.json()["id"]

    loaded = test_client.post(
        f"/engagements/{engagement_id}/load-samples?pack=clean",
        headers=headers,
    )
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["pack"] == "clean"
    assert len(loaded.json()["documents"]) >= 4

    confirmed = test_client.post(
        f"/engagements/{engagement_id}/confirm-scope",
        headers=headers,
        json={"audit_type": "procurement_financial"},
    )
    assert confirmed.status_code == 200, confirmed.text

    analyzed = test_client.post(f"/engagements/{engagement_id}/analyze", headers=headers)
    assert analyzed.status_code == 200, analyzed.text
    rules = {item["rule_id"] for item in analyzed.json()["findings"]}
    assert "AMOUNT_MISMATCH" not in rules
    assert "MISSING_APPROVAL" not in rules


def test_scanned_pack_has_no_extractable_text():
    from app.config import samples_dir
    from app.pdf_text import read_pages

    scanned = samples_dir() / "scanned" / "invoice_scan.pdf"
    assert scanned.is_file()
    pages = read_pages(scanned)
    text = "\n".join(page_text for _, page_text in pages).strip()
    assert text == ""
    png = samples_dir() / "images" / "scanned" / "invoice_scan.png"
    assert png.is_file() and png.stat().st_size > 1000


def test_duplicate_payment_pack_flags_rule(client):
    test_client, _data = client
    token = login(test_client, SENIOR)
    headers = auth(token)
    created = test_client.post(
        "/engagements",
        headers=headers,
        json={"name": "Duplicate payment check", "assign_auditors": False},
    )
    engagement_id = created.json()["id"]
    loaded = test_client.post(
        f"/engagements/{engagement_id}/load-samples?pack=duplicate_payment",
        headers=headers,
    )
    assert loaded.status_code == 200, loaded.text
    test_client.post(
        f"/engagements/{engagement_id}/confirm-scope",
        headers=headers,
        json={"audit_type": "procurement_financial"},
    )
    analyzed = test_client.post(f"/engagements/{engagement_id}/analyze", headers=headers)
    assert analyzed.status_code == 200, analyzed.text
    assert any(item["rule_id"] == "DUPLICATE_PAYMENT" for item in analyzed.json()["findings"])
