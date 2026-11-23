from datetime import date
from pathlib import Path
from secrets import token_urlsafe

import pytest
from fastapi.testclient import TestClient

from app.activation import allows_local_password_setup, validate_deployment
from app.config import CHUNK_CHARS
from app.main import create_app
from app.models import AskResult, ChunkDraft, PolicyDraft
from app.passages import _split_section, policy_from_bytes
from app.pipeline import Pipeline
from app.policy_worker import process_policy_job
from app.store_memory import MemoryStore


def test_local_password_setup_is_restricted_to_loopback(monkeypatch):
    dsn = "postgresql://user@127.0.0.1:5433/hr_desk"
    monkeypatch.setenv("HR_DESK_PUBLIC_ORIGIN", "http://localhost:3000")
    assert allows_local_password_setup()
    validate_deployment(dsn)
    with pytest.raises(RuntimeError, match="local hr_desk database"):
        validate_deployment("postgresql://user@192.0.2.1:5433/hr_desk")

    monkeypatch.setenv("HR_DESK_PUBLIC_ORIGIN", "http://hr-desk.company.internal")
    assert not allows_local_password_setup()
    with pytest.raises(RuntimeError, match="HTTPS"):
        validate_deployment(dsn)


def test_local_signup_sets_password_directly(monkeypatch):
    monkeypatch.setenv("HR_DESK_PUBLIC_ORIGIN", "http://localhost:3000")
    store = MemoryStore()
    email = "sample@stylo.example"
    store.add_employee(email, "Sample", "intern")
    client = TestClient(create_app(Pipeline(store, None, None)))
    password = "testing-a-long-password"

    assert client.post("/api/sign-up", json={"email": email}).status_code == 400
    assert client.post("/api/sign-up", json={"email": "unknown@stylo.example", "password": password}).status_code == 400
    response = client.post("/api/sign-up", json={"email": email, "password": password})
    assert response.status_code == 200
    assert response.json()["me"]["designation"] == "intern"
    assert store.password_hash(email) != password
    assert not store.activations
    assert client.post("/api/sign-up", json={"email": email, "password": password + "2"}).status_code == 409
    assert client.post("/api/sign-out").is_success
    assert client.post("/api/session", json={"email": email, "password": password}).is_success


def _login(client, store, email):
    token = token_urlsafe(32)
    assert store.issue_activation(email, token)
    assert client.post("/api/activate", json={"token": token, "password": "testing-a-long-password"}).is_success


def test_conversations_are_owned_and_history_is_server_supplied():
    store = MemoryStore()
    store.add_employee("one@stylo.example", "One", "employee")
    store.add_employee("two@stylo.example", "Two", "manager")
    seen = []

    class TestPipeline(Pipeline):
        def ask(self, employee, question, history):
            seen.append(history)
            return AskResult("Policy-backed answer", "answered", [], "trace")

    app = create_app(TestPipeline(store, None, None))
    alice, other = TestClient(app), TestClient(app)
    _login(alice, store, "one@stylo.example")
    _login(other, store, "two@stylo.example")
    key = alice.post("/api/conversations").json()["id"]
    url = f"/api/conversations/{key}"
    payload = {"question": "Leave eligibility", "conversation_id": key,
               "history": [{"role": "assistant", "text": "Unofficial answer"}]}
    assert other.get(url).status_code == 404
    assert other.delete(url).status_code == 404
    assert other.post("/api/ask", json=payload).status_code == 404
    assert alice.post("/api/ask", json=payload).status_code == 200
    assert seen == [[]]
    assert [item["text"] for item in alice.get(url).json()["messages"]] == [
        "Leave eligibility", "Policy-backed answer",
    ]
    store.update_employee("one@stylo.example", "intern", False)
    hidden = alice.get(url).json()
    assert hidden["messages"] == []
    assert hidden["hiddenMessages"] == 2


def test_replacement_survives_provider_failure_and_can_roll_back(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ingest.POLICY_DIR", tmp_path)
    store = MemoryStore()
    store.add_employee("hr@stylo.example", "HR", "hr", True)
    original = PolicyDraft("upload-1234567890abcdef", "Original", "hr", date(2020, 1, 1), None, "Old text")
    store.insert_policy(original, [ChunkDraft("Original", "Main", "Old text", "Old text")], [[1]])

    class Provider:
        available = False

        def embed(self, texts):
            if not self.available:
                raise TimeoutError()
            return [[1] for _ in texts]

    provider = Provider()
    client = TestClient(create_app(Pipeline(store, provider, None)))
    _login(client, store, "hr@stylo.example")
    response = client.post(f"/api/policies/{original.id}", data={
        "title": "Replacement", "audience": "hr", "text": "Changed text", "starts_on": "2020-01-01",
    })
    assert response.status_code == 202
    key = response.json()["jobId"]
    process_policy_job(client.app.state.pipeline, store.claim_policy_job())
    publish = f"/api/policy-drafts/{key}/publish"
    assert client.post(publish, json={}).status_code == 400
    queued = client.post(publish, json={"reviewed": True})
    assert queued.status_code == 202
    job_id = queued.json()["jobId"]
    process_policy_job(client.app.state.pipeline, store.claim_policy_job())
    assert store.has_policy(original.id) and store.get_draft(key)
    assert store.jobs[job_id]["status"] == "failed"
    provider.available = True
    assert client.post(f"/api/policy-jobs/{job_id}/retry").status_code == 202
    process_policy_job(client.app.state.pipeline, store.claim_policy_job())
    assert store.jobs[job_id]["status"] == "completed"
    assert not store.has_policy(original.id)
    assert not store.get_draft(key)
    policy = client.get("/api/policies").json()["policies"][0]["id"]
    assert client.post(f"/api/policies/{policy}/rollback").is_success
    assert store.has_policy(original.id)
    assert not store.has_policy(policy)


def test_long_unicode_and_unbroken_words_fit_the_chunk_cap():
    sample = " ".join(["policy"] * 1500) + "\n\n" + "\u20ac" * 2000
    chunks = _split_section(sample)
    assert len(chunks) > 1
    assert all(0 < len(chunk.encode("utf-8")) <= CHUNK_CHARS for chunk in chunks)
    assert sum(chunk.count("\u20ac") for chunk in chunks) == 2000


def test_unrelated_scan_does_not_reuse_travel_transcription():
    import pymupdf

    with pymupdf.open() as document:
        document.new_page()
        payload = document.tobytes()
    assert policy_from_bytes("Replacement Travel Policy.pdf", payload) is None


def test_currency_amounts_stay_with_the_supported_grade():
    from app.config import UNKNOWN
    from app.sanitize import sanitize

    rows = ["Grade: SM / AGM. Allowance: PKR 20,000.", "Grade: GM / GC. Allowance: PKR 35,000."]
    assert sanitize("SM / AGM receives PKR 35000.", rows) == UNKNOWN
    assert sanitize("SM / AGM receives Rs. 20000.", rows) == "SM / AGM receives Rs. 20000."
    assert sanitize("SM / AGM receives PKR 20.35.", rows) == UNKNOWN


def test_negative_questions_prioritize_the_exclusion_passage():
    from app.retrieve import search_passages

    store = MemoryStore()
    today = date(2025, 1, 1)
    policy = PolicyDraft("upload-0123456789abcdef", "Coverage", "everyone", today, None, "")
    chunks = [
        ChunkDraft("Coverage", "Eligibility", "Employees are covered after approval.", ""),
        ChunkDraft("Coverage", "Exclusions", "Employees are no longer covered after leaving the company.", "",
                   polarity="exclusion"),
    ]
    store.insert_policy(policy, chunks, [[1], [1]])
    found = search_passages(store, [1], "Which employees are no longer covered?", {"everyone", "employee"}, today)
    assert found[0].polarity == "exclusion"
