"""Wire the store, embeddings, and model for the app and the checks."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .config import DESK_ROOT, openai_api_key
from .embeddings import FakeEmbedder
from .llm import OpenAIBackend, StubLLM
from .pipeline import Pipeline
from .store_memory import MemoryStore

load_dotenv(DESK_ROOT / ".env")


def sync_samples(store, embedder) -> None:
    from .ingest import load_sample_policies

    _sync(store, embedder, load_sample_policies(), replace_samples=False)


def sync_library(store, embedder) -> None:
    from .ingest import load_office_policies

    office = load_office_policies()
    if office:
        _sync(store, embedder, office, replace_samples=True)
        return
    sync_samples(store, embedder)


def _sync(store, embedder, policies, *, replace_samples: bool) -> None:
    from .ingest import make_chunks as chunk_policy

    if replace_samples:
        store.delete_samples_except(set())
        store.delete_docs_except({policy.id for policy in policies})
    else:
        store.delete_samples_except({policy.id for policy in policies if policy.sample})
    for policy in policies:
        if store.has_policy(policy.id):
            continue
        chunks = chunk_policy(policy)
        vectors = embedder.embed([chunk.embed_text for chunk in chunks])
        store.insert_policy(policy, chunks, vectors)


def open_store():
    mode = os.environ.get("HR_DESK_STORE", "").strip().lower()
    if mode == "memory":
        return MemoryStore()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if mode == "postgres" or (dsn and mode != "memory"):
        if not dsn:
            raise RuntimeError("DATABASE_URL is required when HR_DESK_STORE=postgres.")
        from .store_pg import PostgresStore

        return PostgresStore(dsn)
    return MemoryStore()


def build_embedder(stub: bool = False):
    if stub or not openai_api_key():
        return FakeEmbedder()
    from openai import OpenAI

    return OpenAIBackend(OpenAI(api_key=openai_api_key()))


def build_llm(stub: bool = False):
    if stub or not openai_api_key():
        return StubLLM()
    from openai import OpenAI

    return OpenAIBackend(OpenAI(api_key=openai_api_key()))


def build_pipeline(stub: bool = False) -> Pipeline:
    store = open_store()
    embedder = build_embedder(stub=stub)
    llm = build_llm(stub=stub)
    sync_library(store, embedder)
    return Pipeline(store, embedder, llm)


def memory_pipeline(llm=None, embedder=None) -> Pipeline:
    store = MemoryStore()
    embedder = embedder or FakeEmbedder()
    llm = llm or StubLLM()
    sync_samples(store, embedder)
    return Pipeline(store, embedder, llm)
