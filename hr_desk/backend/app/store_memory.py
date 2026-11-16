"""In-memory store for checks that stop before search. The live app uses Postgres."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from datetime import date, datetime, timezone

from .embeddings import cosine
from .models import ChunkDraft, Employee, Passage, PolicyDraft, TraceRecord
from .textutil import keyword_score


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.employees: dict[str, Employee] = {}
        self.password_hashes: dict[str, str] = {}
        self.sessions: dict[str, str] = {}
        self.policies: dict[str, PolicyDraft] = {}
        self.chunks: list[dict] = []
        self.cache: list[dict] = []
        self.traces: dict[str, TraceRecord] = {}

    def add_employee(self, email: str, name: str, designation: str, is_admin: bool = False) -> None:
        self.employees[email] = Employee(email, name, designation, is_admin)

    def employee(self, email: str) -> Employee | None:
        return self.employees.get(email)

    def password_hash(self, email: str) -> str | None:
        return self.password_hashes.get(email) or None

    def set_password(self, email: str, password_hash: str) -> bool:
        if email not in self.employees or self.password_hashes.get(email):
            return False
        self.password_hashes[email] = password_hash
        return True

    def delete_session(self, token: str) -> None:
        with self._lock:
            self.sessions.pop(token or "", None)

    def create_session(self, email: str) -> str:
        with self._lock:
            token = secrets.token_urlsafe(32)
            self.sessions[token] = email
            return token

    def employee_for_session(self, token: str) -> Employee | None:
        email = self.sessions.get(token or "")
        if not email:
            return None
        return self.employees.get(email)

    def delete_docs_except(self, keep_ids: set[str]) -> None:
        with self._lock:
            removed = {
                policy_id
                for policy_id in self.policies
                if policy_id.startswith("doc-") and policy_id not in keep_ids
            }
            for policy_id in removed:
                self.policies.pop(policy_id, None)
            self.chunks = [chunk for chunk in self.chunks if chunk["policy_id"] not in removed]
            if removed:
                self.cache.clear()

    def has_policy(self, policy_id: str) -> bool:
        return policy_id in self.policies

    def delete_policy(self, policy_id: str) -> bool:
        with self._lock:
            if policy_id not in self.policies:
                return False
            self.policies.pop(policy_id, None)
            self.chunks = [chunk for chunk in self.chunks if chunk["policy_id"] != policy_id]
            self.cache.clear()
            return True

    def insert_policy(
        self,
        policy: PolicyDraft,
        chunks: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise RuntimeError("Each policy section needs an embedding.")
        with self._lock:
            self.policies[policy.id] = policy
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                self.chunks.append(
                    {
                        "id": f"{policy.id}:{index}",
                        "policy_id": policy.id,
                        "title": policy.title,
                        "section_label": chunk.section_label,
                        "heading": chunk.heading,
                        "body": chunk.body,
                        "embed_text": chunk.embed_text,
                        "embedding": vector,
                        "heading_path": chunk.heading_path,
                        "content_type": chunk.content_type,
                        "page": chunk.page,
                        "image_path": chunk.image_path,
                        "polarity": chunk.polarity,
                        "audience": policy.audience,
                        "effective_from": policy.effective_from,
                        "effective_to": policy.effective_to,
                    }
                )
            self.cache.clear()

    def list_policies(self) -> list[PolicyDraft]:
        return list(self.policies.values())

    def policy_version(self) -> str:
        payload = []
        for policy in sorted(self.policies.values(), key=lambda item: item.id):
            payload.append(
                {
                    "id": policy.id,
                    "audience": policy.audience,
                    "effective_from": policy.effective_from.isoformat(),
                    "effective_to": policy.effective_to.isoformat() if policy.effective_to else "",
                }
            )
        for chunk in self.chunks:
            payload.append({"chunk": chunk["id"], "body": chunk["body"]})
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def candidates(
        self,
        embedding: list[float],
        query: str,
        audiences: set[str],
        today: date,
        limit: int,
    ) -> list[Passage]:
        found: list[Passage] = []
        for chunk in self.chunks:
            if chunk["audience"] not in audiences:
                continue
            if chunk["effective_from"] > today:
                continue
            if chunk["effective_to"] and chunk["effective_to"] < today:
                continue
            passage = _passage(chunk, cosine(embedding, chunk["embedding"]))
            passage.kw_score = keyword_score(
                query,
                f"{chunk['section_label']} {chunk.get('heading_path', '')} {chunk['heading']} {chunk['body']}",
            )
            found.append(passage)
        found.sort(key=lambda passage: (0.65 * max(passage.vec_score, 0.0) + 0.35 * passage.kw_score), reverse=True)
        return found[:limit]

    def cache_lookup(
        self,
        embedding: list[float],
        access: str,
        version: str,
        threshold: float,
    ) -> dict | None:
        best: dict | None = None
        best_score = threshold
        for row in self.cache:
            if row["access_key"] != access or row["policy_version"] != version:
                continue
            score = cosine(embedding, row["embedding"])
            if score >= best_score:
                best = {**row, "similarity": score}
                best_score = score
        return best

    def cache_store(self, row: dict) -> None:
        with self._lock:
            self.cache.append(row)

    def add_trace(self, trace: TraceRecord) -> None:
        with self._lock:
            self.traces[trace.id] = trace

    def list_traces(self, limit: int = 50) -> list[TraceRecord]:
        rows = sorted(self.traces.values(), key=lambda trace: trace.created_at, reverse=True)
        return rows[:limit]

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        return self.traces.get(trace_id)


def _passage(chunk: dict, vec_score: float) -> Passage:
    return Passage(
        id=chunk["id"],
        policy_id=chunk["policy_id"],
        title=chunk["title"],
        section_label=chunk["section_label"],
        heading=chunk["heading"],
        body=chunk["body"],
        audience=chunk["audience"],
        effective_from=chunk["effective_from"],
        effective_to=chunk["effective_to"],
        vec_score=vec_score,
        heading_path=chunk.get("heading_path", ""),
        content_type=chunk.get("content_type", "section"),
        page=chunk.get("page"),
        image_path=chunk.get("image_path", ""),
        polarity=chunk.get("polarity", ""),
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
