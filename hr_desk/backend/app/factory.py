"""Wire the store, embeddings, and model."""

from __future__ import annotations

import os

from .activation import allows_local_password_setup, validate_deployment
from .config import openai_api_key
from .llm import OpenAIBackend
from .pipeline import Pipeline

def index_missing_policies(store, embedder, policies) -> None:
    from .ingest import make_chunks as chunk_policy

    for policy in policies:
        if store.has_policy(policy.id):
            continue
        chunks = policy.chunks if policy.chunks else chunk_policy(policy)
        vectors = embedder.embed([chunk.embed_text for chunk in chunks])
        store.insert_policy(policy, chunks, vectors)


def open_store():
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("DATABASE_URL is required.")
    validate_deployment(dsn)
    from .store_pg import PostgresStore

    local_setup = allows_local_password_setup()
    store = PostgresStore(dsn)
    if not local_setup:
        with store.conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM employees WHERE split_part(email, '@', 2) = 'stylo.example')")
            sample_accounts_present = cur.fetchone()[0]
        if sample_accounts_present:
            store.conn.close()
            raise RuntimeError("Remove sample employee accounts before enabling company access.")
    store.ping()
    return store


def build_embedder(store):
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    from openai import OpenAI

    def reserve():
        store.consume_budget([("provider:daily", 3000, 86400)])

    return OpenAIBackend(OpenAI(api_key=key, max_retries=0), reserve)


def build_pipeline() -> Pipeline:
    store = open_store()
    provider = build_embedder(store)
    return Pipeline(store, provider, provider)
