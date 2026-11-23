"""Integration checks. Point HR_DESK_TEST_DATABASE_URL at a disposable test database."""

import os
from datetime import date, timedelta
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.access import allowed_audiences
from app.models import ChunkDraft, PolicyDraft
from app.operations import BudgetExceeded
from app.store_pg import PostgresStore


def test_postgres_accounts_policy_revisions_and_request_budget():
    dsn = os.environ.get("HR_DESK_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set HR_DESK_TEST_DATABASE_URL to run PostgreSQL integration checks.")
    assert conninfo_to_dict(dsn).get("dbname", "").endswith("_test")
    first, second = PostgresStore(dsn, migrate=True), PostgresStore(dsn)
    key = uuid4().hex[:16]
    email = f"tester-{key}@stylo.example"
    other = f"other-{key}@stylo.example"
    original = f"upload-{key}"
    replacement = f"doc-{key}"
    vector = [1.0, *([0.0] * 1535)]
    today = date.today()
    try:
        assert first.create_employee(email, "Tester", "manager", True)
        assert first.create_employee(other, "Other", "intern")
        token = token_urlsafe(32)
        assert first.issue_activation(email, token)
        assert second.redeem_activation(token, "example-stored-hash").email == email
        assert first.redeem_activation(token, "unused") is None
        session = first.create_session(email)
        assert second.employee_for_session(session).designation == "manager"
        chat = first.create_conversation(email)
        assert second.conversation(other, chat) is None
        first.append_exchange(email, chat, {"text": "Question"}, {"text": "Answer"})
        assert len(second.conversation(email, chat)) == 2

        limits = [(f"test:{key}", 1, 3600)]
        first.consume_budget(limits)
        with pytest.raises(BudgetExceeded):
            second.consume_budget(limits)

        row = ChunkDraft("Travel", "Fuel Entitlement", "SM / AGM: eligible", "fuel", content_type="table")
        first.insert_policy(PolicyDraft(original, "Travel", "everyone", today, None, "Fuel"), [row], [vector])
        assert any(p.policy_id == original for p in second.candidates(
            vector, "fuel", set(allowed_audiences("manager")), today, 20,
        ))
        manager = set(allowed_audiences("manager"))
        assert second.candidates(vector, "fuel", manager, today, 20, policy_ids=[original])
        assert second.candidates(vector, "fuel", manager, today, 20, policy_ids=[replacement]) == []
        assert second.heading_hits(["Fuel Entitlement"], manager, today, policy_ids=[original])
        assert second.heading_hits(["Fuel Entitlement"], manager, today, policy_ids=[replacement]) == []
        assert second.clause_hits(["3.2.1"], manager, today, policy_ids=[original]) == []
        assert second.printed_page_hits(2, manager, today, policy_ids=[original]) == []
        assert all(p.policy_id != original for p in second.candidates(
            vector, "fuel", set(allowed_audiences("intern")), today, 20,
        ))
        version = first.policy_version()
        first.cache_store({
            "id": key,
            "access_key": "manager",
            "policy_version": version,
            "question": "Fuel entitlement?",
            "answer": "Check the fuel policy.",
            "citations": [],
            "outcome": "answered",
        })
        assert second.cache_lookup("Fuel entitlement?", "manager", version)["answer"] == "Check the fuel policy."
        assert second.cache_lookup("Fuel entitlement?", "intern", version) is None
        first.save_draft(key, {"title": "Replacement"})
        first.insert_policy(PolicyDraft(replacement, "Replacement", "hr", today, None, "Fuel"),
                            [row], [vector], replaces=original, draft_key=key, actor=email)
        assert not second.has_policy(original) and second.has_policy(replacement)
        assert second.get_draft(key) is None
        assert second.rollback_policy(replacement, email)
        assert first.has_policy(original) and not first.has_policy(replacement)

        scheduled = f"upload-{key[::-1]}"
        future = today + timedelta(days=2)
        first.insert_policy(PolicyDraft(scheduled, "Scheduled", "hr", future, None, "New fuel rule"),
                            [row], [vector], replaces=original, as_of=today)
        hr = set(allowed_audiences("hr"))
        assert {p.policy_id for p in second.candidates(vector, "fuel", hr, future - timedelta(days=1), 20)} == {original}
        assert {p.policy_id for p in second.candidates(vector, "fuel", hr, future, 20)} == {scheduled}
        assert second.passages_by_id([f"{original}:0"])[0].effective_to == future - timedelta(days=1)
        assert first.update_policy_access(scheduled, "hr", future + timedelta(days=1), None, as_of=today)
        assert {p.policy_id for p in second.candidates(vector, "fuel", hr, future, 20)} == {original}
        assert {p.policy_id for p in second.candidates(vector, "fuel", hr, future + timedelta(days=1), 20)} == {scheduled}
        assert second.rollback_policy(scheduled, email)
        assert {p.policy_id for p in second.candidates(vector, "fuel", hr, future, 20)} == {original}

        job_id = first.enqueue_policy_job("prepare", {"title": "Test upload"}, email, b"upload")
        first_claim = first.claim_policy_job()
        assert first_claim["id"] == job_id and first_claim["upload"] == b"upload"
        assert second.claim_policy_job() is None
        with first.conn.cursor() as cur:
            cur.execute("UPDATE policy_jobs SET lease_until = now() - interval '1 second' WHERE id = %s", (job_id,))
        recovered = second.claim_policy_job()
        assert recovered["id"] == job_id and recovered["claim"] != first_claim["claim"]
        with pytest.raises(ValueError):
            first.save_draft(job_id, {"title": "Stale"}, job_claim=(job_id, first_claim["claim"]))
        second.save_draft(job_id, {"title": "Test upload"}, job_claim=(job_id, recovered["claim"]))
        assert first.get_draft(job_id)["title"] == "Test upload"
        assert first.list_policy_jobs()[0]["status"] == "completed"
    finally:
        with first.conn.cursor() as cur:
            cur.execute("DELETE FROM policy_drafts WHERE id = %s", (key,))
            cur.execute("DELETE FROM policies WHERE id = ANY(%s)", ([original, replacement, f"upload-{key[::-1]}"],))
            cur.execute("DELETE FROM request_budget WHERE scope = %s", (f"test:{key}",))
            cur.execute("DELETE FROM admin_actions WHERE email = %s", (email,))
            cur.execute("DELETE FROM policy_drafts WHERE id IN (SELECT id FROM policy_jobs WHERE actor = %s)", (email,))
            cur.execute("DELETE FROM policy_jobs WHERE actor = %s", (email,))
        first.delete_employee(email)
        first.delete_employee(other)
        first.conn.close()
        second.conn.close()
