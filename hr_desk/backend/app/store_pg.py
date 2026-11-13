"""Postgres + pgvector store. One database for policies, saved answers, and traces."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from datetime import date, datetime

from psycopg.types.json import Jsonb

from .access import PEOPLE
from .models import ChunkDraft, Employee, Passage, PolicyDraft, TraceRecord
from .store_memory import utc_now

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS employees (
  email TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  designation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  email TEXT NOT NULL REFERENCES employees(email),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  audience TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,
  sample BOOLEAN NOT NULL,
  body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_chunks (
  id TEXT PRIMARY KEY,
  policy_id TEXT NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
  section_label TEXT NOT NULL,
  heading TEXT NOT NULL,
  body TEXT NOT NULL,
  embed_text TEXT NOT NULL,
  embedding vector(1536) NOT NULL,
  search_text tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(section_label, '') || ' ' || coalesce(body, ''))
  ) STORED,
  audience TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE
);

CREATE TABLE IF NOT EXISTS answer_cache (
  id TEXT PRIMARY KEY,
  embedding vector(1536) NOT NULL,
  access_key TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  citations JSONB NOT NULL,
  outcome TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS traces (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  email TEXT NOT NULL,
  question TEXT NOT NULL,
  outcome TEXT NOT NULL,
  payload JSONB NOT NULL
);
"""


def _vector(values: list[float]):
    from pgvector import Vector

    # A bare Python list is sent as a float array, and <=> has no match for that.
    return Vector(values)


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        self._lock = threading.Lock()
        try:
            self.conn = psycopg.connect(dsn, connect_timeout=5)
        except Exception as exc:
            raise RuntimeError(
                "Could not connect to Postgres. Start Docker, or set HR_DESK_STORE=memory."
            ) from exc
        # Stay in autocommit. A bare query otherwise opens a transaction, and the
        # next transaction() block only releases a savepoint inside it, so writes
        # never become visible and disappear when the process stops.
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self._migrate()

    def _recover(self) -> None:
        from psycopg.pq import TransactionStatus

        if self.conn.info.transaction_status == TransactionStatus.INERROR:
            self.conn.rollback()

    def _migrate(self) -> None:
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            cur.execute(_SCHEMA)
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS policy_chunks_embedding_idx
                ON policy_chunks USING hnsw (embedding vector_cosine_ops)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS policy_chunks_search_idx
                ON policy_chunks USING gin (search_text)
                """
            )
            for email, name, designation in PEOPLE:
                cur.execute(
                    """
                    INSERT INTO employees (email, name, designation)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) DO UPDATE
                    SET name = EXCLUDED.name, designation = EXCLUDED.designation
                    """,
                    (email, name, designation),
                )

    def employee(self, email: str) -> Employee | None:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                "SELECT email, name, designation FROM employees WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return Employee(*row)

    def people(self) -> list[Employee]:
        with self._lock, self.conn.cursor() as cur:
            cur.execute("SELECT email, name, designation FROM employees ORDER BY name")
            return [Employee(*row) for row in cur.fetchall()]

    def create_session(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            cur.execute(
                "INSERT INTO sessions (token, email) VALUES (%s, %s)",
                (token, email),
            )
        return token

    def employee_for_session(self, token: str) -> Employee | None:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.email, e.name, e.designation
                FROM sessions s
                JOIN employees e ON e.email = s.email
                WHERE s.token = %s
                """,
                (token,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return Employee(*row)

    def delete_samples_except(self, keep_ids: set[str]) -> None:
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            if keep_ids:
                cur.execute(
                    "DELETE FROM policies WHERE sample = TRUE AND NOT (id = ANY(%s))",
                    (list(keep_ids),),
                )
            else:
                cur.execute("DELETE FROM policies WHERE sample = TRUE")
            if cur.rowcount:
                cur.execute("DELETE FROM answer_cache")

    def delete_docs_except(self, keep_ids: set[str]) -> None:
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            if keep_ids:
                cur.execute(
                    "DELETE FROM policies WHERE id LIKE 'doc-%%' AND NOT (id = ANY(%s))",
                    (list(keep_ids),),
                )
            else:
                cur.execute("DELETE FROM policies WHERE id LIKE 'doc-%%'")
            if cur.rowcount:
                cur.execute("DELETE FROM answer_cache")

    def has_policy(self, policy_id: str) -> bool:
        with self._lock, self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM policies WHERE id = %s", (policy_id,))
            return cur.fetchone() is not None

    def insert_policy(
        self,
        policy: PolicyDraft,
        chunks: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise RuntimeError("Each policy section needs an embedding.")
        for vector in vectors:
            if len(vector) != 1536:
                raise RuntimeError("Embeddings must have 1536 numbers.")
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            cur.execute(
                """
                INSERT INTO policies
                  (id, title, audience, effective_from, effective_to, sample, body)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    policy.id,
                    policy.title,
                    policy.audience,
                    policy.effective_from,
                    policy.effective_to,
                    policy.sample,
                    policy.body,
                ),
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                cur.execute(
                    """
                    INSERT INTO policy_chunks
                      (id, policy_id, section_label, heading, body, embed_text, embedding,
                       audience, effective_from, effective_to)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        f"{policy.id}:{index}",
                        policy.id,
                        chunk.section_label,
                        chunk.heading,
                        chunk.body,
                        chunk.embed_text,
                        _vector(vector),
                        policy.audience,
                        policy.effective_from,
                        policy.effective_to,
                    ),
                )
            cur.execute("DELETE FROM answer_cache")

    def list_policies(self) -> list[PolicyDraft]:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, audience, effective_from, effective_to, sample, body
                FROM policies
                ORDER BY title, effective_from
                """
            )
            return [
                PolicyDraft(
                    id=row[0],
                    title=row[1],
                    audience=row[2],
                    effective_from=row[3],
                    effective_to=row[4],
                    sample=row[5],
                    body=row[6],
                )
                for row in cur.fetchall()
            ]

    def has_samples(self) -> bool:
        with self._lock, self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM policies WHERE sample = TRUE LIMIT 1")
            return cur.fetchone() is not None

    def policy_version(self) -> str:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, audience, effective_from::text, COALESCE(effective_to::text, '')
                FROM policies
                ORDER BY id
                """
            )
            policies = cur.fetchall()
            cur.execute("SELECT id, body FROM policy_chunks ORDER BY id")
            chunks = cur.fetchall()
        raw = json.dumps({"policies": policies, "chunks": chunks}, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def candidates(
        self,
        embedding: list[float],
        query: str,
        audiences: set[str],
        today: date,
        limit: int,
    ) -> list[Passage]:
        audience_list = list(audiences)
        vector = _vector(embedding)
        self._recover()
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.policy_id, p.title, c.section_label, c.heading, c.body,
                       c.audience, c.effective_from, c.effective_to,
                       1 - (c.embedding <=> %s) AS vec_score
                FROM policy_chunks c
                JOIN policies p ON p.id = c.policy_id
                WHERE c.audience = ANY(%s)
                  AND c.effective_from <= %s
                  AND (c.effective_to IS NULL OR c.effective_to >= %s)
                ORDER BY c.embedding <=> %s
                LIMIT %s
                """,
                (vector, audience_list, today, today, vector, limit),
            )
            rows = {row[0]: row for row in cur.fetchall()}
            if query.strip():
                cur.execute(
                    """
                    SELECT c.id, c.policy_id, p.title, c.section_label, c.heading, c.body,
                           c.audience, c.effective_from, c.effective_to,
                           1 - (c.embedding <=> %s) AS vec_score
                    FROM policy_chunks c
                    JOIN policies p ON p.id = c.policy_id
                    WHERE c.audience = ANY(%s)
                      AND c.effective_from <= %s
                      AND (c.effective_to IS NULL OR c.effective_to >= %s)
                      AND c.search_text @@ plainto_tsquery('english', %s)
                    LIMIT %s
                    """,
                    (vector, audience_list, today, today, query, limit),
                )
                for row in cur.fetchall():
                    rows[row[0]] = row
        return [_row_passage(row) for row in rows.values()]

    def cache_lookup(
        self,
        embedding: list[float],
        access: str,
        version: str,
        threshold: float,
    ) -> dict | None:
        vector = _vector(embedding)
        self._recover()
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT answer, citations, outcome, 1 - (embedding <=> %s) AS sim, question
                FROM answer_cache
                WHERE access_key = %s AND policy_version = %s
                ORDER BY embedding <=> %s
                LIMIT 1
                """,
                (vector, access, version, vector),
            )
            row = cur.fetchone()
        if not row or row[3] < threshold:
            return None
        return {
            "answer": row[0],
            "citations": row[1],
            "outcome": row[2],
            "similarity": row[3],
            "question": row[4],
        }

    def cache_store(self, row: dict) -> None:
        self._recover()
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            cur.execute(
                """
                INSERT INTO answer_cache
                  (id, embedding, access_key, policy_version, question, answer, citations, outcome)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["id"],
                    _vector(row["embedding"]),
                    row["access_key"],
                    row["policy_version"],
                    row["question"],
                    row["answer"],
                    Jsonb(row["citations"]),
                    row["outcome"],
                ),
            )

    def add_trace(self, trace: TraceRecord) -> None:
        payload = _trace_payload(trace)
        self._recover()
        with self._lock, self.conn.cursor() as cur, self.conn.transaction():
            cur.execute(
                """
                INSERT INTO traces (id, created_at, email, question, outcome, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    trace.id,
                    trace.created_at,
                    trace.email,
                    trace.question,
                    trace.outcome,
                    Jsonb(payload),
                ),
            )

    def list_traces(self, limit: int = 50) -> list[TraceRecord]:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM traces
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [_trace_from_payload(row[0]) for row in cur.fetchall()]

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        with self._lock, self.conn.cursor() as cur:
            cur.execute("SELECT payload FROM traces WHERE id = %s", (trace_id,))
            row = cur.fetchone()
        if not row:
            return None
        return _trace_from_payload(row[0])


def _row_passage(row: tuple) -> Passage:
    effective_to = row[8]
    if isinstance(effective_to, datetime):
        effective_to = effective_to.date()
    return Passage(
        id=row[0],
        policy_id=row[1],
        title=row[2],
        section_label=row[3],
        heading=row[4],
        body=row[5],
        audience=row[6],
        effective_from=row[7],
        effective_to=effective_to,
        vec_score=float(row[9] or 0),
    )


def _trace_payload(trace: TraceRecord) -> dict:
    return {
        "id": trace.id,
        "created_at": trace.created_at,
        "email": trace.email,
        "name": trace.name,
        "designation": trace.designation,
        "question": trace.question,
        "guardrail": trace.guardrail,
        "guardrail_reason": trace.guardrail_reason,
        "classifier_called": trace.classifier_called,
        "cache": trace.cache,
        "rewritten_question": trace.rewritten_question,
        "history_note": trace.history_note,
        "search": trace.search,
        "sections": trace.sections,
        "withheld": trace.withheld,
        "scores": trace.scores,
        "model": trace.model,
        "tokens_in": trace.tokens_in,
        "tokens_out": trace.tokens_out,
        "latency_ms": trace.latency_ms,
        "outcome": trace.outcome,
        "answer": trace.answer,
        "citations": [{"label": item.label, "text": item.text} for item in trace.citations],
        "steps": trace.steps,
        "prompt_version": trace.prompt_version,
    }


def _trace_from_payload(payload: dict) -> TraceRecord:
    from .models import Citation

    return TraceRecord(
        id=payload["id"],
        created_at=payload["created_at"],
        email=payload["email"],
        name=payload["name"],
        designation=payload["designation"],
        question=payload["question"],
        guardrail=payload["guardrail"],
        guardrail_reason=payload["guardrail_reason"],
        classifier_called=payload["classifier_called"],
        cache=payload["cache"],
        rewritten_question=payload["rewritten_question"],
        history_note=payload["history_note"],
        search=payload["search"],
        sections=payload.get("sections") or [],
        withheld=payload.get("withheld", False),
        scores=payload.get("scores") or [],
        model=payload.get("model"),
        tokens_in=payload.get("tokens_in") or 0,
        tokens_out=payload.get("tokens_out") or 0,
        latency_ms=payload.get("latency_ms") or 0,
        outcome=payload.get("outcome") or "",
        answer=payload.get("answer") or "",
        citations=[Citation(item["label"], item["text"]) for item in payload.get("citations") or []],
        steps=payload.get("steps") or [],
        prompt_version=payload.get("prompt_version") or "",
    )
