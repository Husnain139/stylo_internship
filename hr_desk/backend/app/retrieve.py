"""Hybrid search: vector similarity plus the words the employee actually used."""

from __future__ import annotations

from datetime import date

from .config import (
    MAX_PASSAGES,
    MIN_VECTOR_SCORE,
    PASSAGE_SCORE_WINDOW,
    RETRIEVE_CANDIDATES,
    RETRIEVE_TOP_K,
)
from .models import Passage
from .textutil import keyword_score


def _keep(passage: Passage) -> bool:
    if passage.kw_score >= 0.67:
        return True
    if passage.vec_score >= 0.55:
        return True
    return passage.vec_score >= MIN_VECTOR_SCORE and passage.kw_score >= 0.34


def search_passages(store, embedding: list[float], query: str, audiences: set[str], today: date) -> list[Passage]:
    raw = store.candidates(embedding, query, audiences, today, RETRIEVE_CANDIDATES)
    kept: list[Passage] = []
    for passage in raw:
        passage.kw_score = keyword_score(query, f"{passage.section_label} {passage.heading} {passage.body}")
        passage.score = 0.65 * max(passage.vec_score, 0.0) + 0.35 * passage.kw_score
        if _keep(passage):
            kept.append(passage)
    kept.sort(key=lambda passage: passage.score, reverse=True)
    return kept[:RETRIEVE_TOP_K]


def select_passages(passages: list[Passage]) -> list[Passage]:
    if not passages:
        return []
    best = passages[0].score
    chosen = [passage for passage in passages if passage.score >= best - PASSAGE_SCORE_WINDOW]
    return chosen[:MAX_PASSAGES]
