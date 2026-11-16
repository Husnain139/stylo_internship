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
from .textutil import keyword_score, token_list, token_set


def _keep(passage: Passage) -> bool:
    if passage.kw_score >= 0.67:
        return True
    if passage.vec_score >= 0.55:
        return True
    if passage.vec_score >= MIN_VECTOR_SCORE and passage.kw_score >= 0.34:
        return True
    # A one-letter slip shares few embedding dimensions, so the word match has to be enough.
    return bool(getattr(passage, "typo_match", False)) and passage.kw_score >= 0.34


_NEGATIVE = {"not", "no", "excluded", "cease", "without", "longer"}


def search_passages(store, embedding: list[float], query: str, audiences: set[str], today: date) -> list[Passage]:
    raw = store.candidates(embedding, query, audiences, today, RETRIEVE_CANDIDATES)
    words = token_set(query)
    negative = bool(words & _NEGATIVE)
    asks_for_form = bool(words & {"template", "form", "details"})
    kept: list[Passage] = []
    for passage in raw:
        haystack = f"{passage.section_label} {passage.heading_path} {passage.heading} {passage.body}"
        passage.kw_score = keyword_score(query, haystack)
        passage.typo_match = _typo_match(query, haystack)
        passage.score = 0.65 * max(passage.vec_score, 0.0) + 0.35 * passage.kw_score
        if negative and passage.polarity == "exclusion":
            passage.score += 0.2
        if asks_for_form and passage.content_type == "form":
            passage.score += 0.15
        if _keep(passage):
            kept.append(passage)
    kept = _prefer_distinctive(query, kept)
    kept.sort(key=lambda passage: passage.score, reverse=True)
    return kept[:RETRIEVE_TOP_K]


def _typo_match(query: str, text: str) -> bool:
    wanted = [token for token in set(token_list(query)) if len(token) >= 5]
    found = token_set(text)
    found_by_length: dict[int, list[str]] = {}
    for token in found:
        found_by_length.setdefault(len(token), []).append(token)
    for token in wanted:
        if token in found:
            continue
        if any(_one_edit(token, other) for other in _similar_length(token, found_by_length)):
            return True
    return False


def _similar_length(token: str, found_by_length: dict[int, list[str]]) -> list[str]:
    nearby: list[str] = []
    for length in (len(token) - 1, len(token), len(token) + 1):
        nearby.extend(found_by_length.get(length, []))
    return nearby


def _one_edit(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    if len(left) > len(right):
        left, right = right, left
    for index in range(len(right)):
        if left == right[:index] + right[index + 1 :]:
            return True
    return False


def _prefer_distinctive(query: str, passages: list[Passage]) -> list[Passage]:
    """Keep the passages that match the specific words, such as summary or retail."""
    if len(passages) < 2:
        return passages
    distinctive = [token for token in set(token_list(query)) if len(token) >= 5]

    def hits(passage: Passage) -> int:
        text = f"{passage.heading_path} {passage.heading} {passage.body}"
        return sum(1 for token in distinctive if keyword_score(token, text) > 0)

    best = max(hits(passage) for passage in passages)
    if best <= 0:
        return passages
    narrowed = [passage for passage in passages if hits(passage) == best]
    return narrowed or passages


def select_passages(passages: list[Passage]) -> list[Passage]:
    if not passages:
        return []
    best = passages[0].score
    chosen = [passage for passage in passages if passage.score >= best - PASSAGE_SCORE_WINDOW]
    return chosen[:MAX_PASSAGES]
