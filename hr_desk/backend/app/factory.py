"""Wire the store, embeddings, and model."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .config import DESK_ROOT, openai_api_key
from .llm import OpenAIBackend
from .pipeline import Pipeline

load_dotenv(DESK_ROOT / ".env")


def sync_library(store, embedder) -> None:
    from .ingest import load_office_policies

    office = load_office_policies()
    if not office:
        return
    _sync(store, embedder, office)


def _sync(store, embedder, policies) -> None:
    from .ingest import make_chunks as chunk_policy

    store.delete_docs_except({policy.id for policy in policies})
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
    from .store_pg import PostgresStore

    return PostgresStore(dsn)


def build_embedder():
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    from openai import OpenAI

    return OpenAIBackend(OpenAI(api_key=key))


def build_llm():
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    from openai import OpenAI

    return OpenAIBackend(OpenAI(api_key=key))


def build_pipeline() -> Pipeline:
    store = open_store()
    embedder = build_embedder()
    llm = build_llm()
    sync_library(store, embedder)
    return Pipeline(store, embedder, llm)
