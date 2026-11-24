"""Hybrid search: vector similarity plus the words the employee actually used."""

from __future__ import annotations

import re
from datetime import date

from .config import (
    MAX_PASSAGES,
    MIN_VECTOR_SCORE,
    PASSAGE_SCORE_WINDOW,
    RERANK_FLOOR,
    RETRIEVE_CANDIDATES,
    RETRIEVE_TOP_K,
    RRF_K,
)
from .clauses import asked_clause, asked_page, contains_clause, heading_has_phrase, heading_phrases
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
_GENERIC = {"short", "brief", "summary", "point", "points", "section", "clause", "heading", "explain", "describe"}


def search_passages(
    store, embedding: list[float], query: str, audiences: set[str], today: date,
    *, policy_ids: list[str] | None = None,
) -> list[Passage]:
    scope = {} if policy_ids is None else {"policy_ids": policy_ids}
    raw = store.candidates(embedding, query, audiences, today, RETRIEVE_CANDIDATES, **scope)
    number = asked_clause(query)
    phrases = heading_phrases(query)
    page_number = asked_page(query)
    seen = {passage.id for passage in raw}
    if number and hasattr(store, "clause_hits"):
        for extra in store.clause_hits([number], audiences, today, **scope):
            if extra.id not in seen:
                raw.append(extra)
                seen.add(extra.id)
    if phrases and hasattr(store, "heading_hits"):
        for extra in store.heading_hits(phrases, audiences, today, **scope):
            if extra.id not in seen:
                raw.append(extra)
                seen.add(extra.id)
    if page_number and hasattr(store, "printed_page_hits"):
        for extra in store.printed_page_hits(page_number, audiences, today, **scope):
            if extra.id not in seen:
                raw.append(extra)
                seen.add(extra.id)
    words = token_set(query)
    negative = bool(words & _NEGATIVE)
    asks_for_form = bool(words & {"template", "form", "details"})
    heading_order = [passage.id for passage in raw if _names_this(passage, phrases, page_number)]
    if number:
        heading_order.extend(
            passage.id for passage in raw
            if contains_clause(f"{passage.heading}\n{passage.body}", number) and passage.id not in heading_order
        )
    for passage in raw:
        # The document title sits in section_label. Score the heading path and the body apart from it.
        passage.heading_kw = keyword_score(query, f"{passage.heading_path} {passage.heading}")
        passage.body_kw = keyword_score(query, passage.body)
        passage.kw_score = max(passage.heading_kw, passage.body_kw)
        passage.typo_match = _typo_match(query, f"{passage.heading_path} {passage.heading} {passage.body}")
    by_vector = sorted(raw, key=lambda passage: passage.vec_score, reverse=True)
    by_keyword = sorted(raw, key=lambda passage: passage.kw_score, reverse=True)
    vector_order = [passage.id for passage in by_vector if passage.vec_score > 0]
    keyword_order = [passage.id for passage in by_keyword if passage.kw_score > 0]
    rrf: dict[str, float] = {}
    for order in (vector_order, keyword_order, heading_order):
        for rank, passage_id in enumerate(order, start=1):
            rrf[passage_id] = rrf.get(passage_id, 0.0) + 1.0 / (RRF_K + rank)
    explicit = set(heading_order)
    pool_ids = {passage.id for passage in sorted(raw, key=lambda item: rrf.get(item.id, 0.0), reverse=True)[:20]}
    pool_ids.update(explicit)
    kept: list[Passage] = []
    for passage in raw:
        if passage.id not in pool_ids:
            continue
        passage.score = _rerank(passage, rrf.get(passage.id, 0.0))
        if negative and passage.polarity == "exclusion":
            passage.score += 0.02
        if asks_for_form and passage.content_type == "form":
            passage.score += 0.02
        if passage.id in explicit or _keep(passage):
            kept.append(passage)
    kept.sort(key=lambda passage: passage.score, reverse=True)
    def protected(passage: Passage) -> bool:
        if number and contains_clause(f"{passage.heading}\n{passage.body}", number):
            return True
        return _names_this(passage, phrases, page_number)

    if number or phrases or page_number:
        named_passages = [passage for passage in kept if protected(passage)]
        others = [passage for passage in kept if passage not in named_passages]
        kept = named_passages + _prefer_distinctive(query, others)
    else:
        kept = _prefer_distinctive(query, kept)
    kept.sort(key=lambda passage: passage.score, reverse=True)
    named = [passage for passage in kept if _phrase_count(passage, phrases)]
    if named:
        best = max(_phrase_count(passage, phrases) for passage in named)
        named = [passage for passage in named if _phrase_count(passage, phrases) == best]
    on_page = [passage for passage in kept if _on_printed_page(passage, page_number, kept)]
    if named or on_page:
        merged = []
        seen_ids = set()
        for passage in named + on_page:
            if passage.id in seen_ids:
                continue
            seen_ids.add(passage.id)
            merged.append(passage)
        if merged:
            top = max(passage.score for passage in merged)
            for passage in merged:
                passage.score = top
        return _with_distance_rule(store, query, merged[:16], audiences, today)
    if kept and kept[0].content_type == "table" and hasattr(store, "heading_rows"):
        rows = store.heading_rows(kept[0].policy_id, kept[0].heading, audiences, today)
        if len(rows) > 1:
            scores = {passage.id: passage.score for passage in kept}
            rows.sort(key=lambda passage: scores.get(passage.id, 0.0), reverse=True)
            for row in rows:
                row.score = scores.get(row.id, 0.0)
            kept = rows
    if kept and kept[0].score < RERANK_FLOOR and not (named or on_page):
        return []
    limit = 16 if kept and kept[0].content_type == "table" and len(kept) > RETRIEVE_TOP_K else RETRIEVE_TOP_K
    return _with_distance_rule(store, query, kept[:limit], audiences, today)


def _rerank(passage: Passage, rrf: float) -> float:
    """Order the fused candidates. A title-only passage loses to a real section."""
    short = 0.04 if len(passage.body.encode("utf-8")) < 80 else 0.0
    return rrf + 0.025 * passage.heading_kw + 0.01 * passage.body_kw - short


def _with_distance_rule(store, query: str, passages: list[Passage], audiences: set[str], today: date) -> list[Passage]:
    asked = bool(re.search(r"\b300\b", query) and re.search(r"\b(?:km|kilometers?|rule|allowance|distance)\b", query, re.I))
    rate = any(re.search(r"daily allowance|fuel entitlement|hotel entitlement", passage.heading, re.I) for passage in passages)
    if not asked and not rate:
        return passages
    if any(re.search(r"\b300\b", passage.body) and re.search(r"round trip", passage.body, re.I) for passage in passages):
        return passages
    if not hasattr(store, "heading_hits"):
        return passages
    for extra in store.heading_hits(["daily allowance"], audiences, today):
        if re.search(r"\b300\b", extra.body) and re.search(r"round trip", extra.body, re.I):
            if all(passage.id != extra.id for passage in passages):
                return [*passages, extra]
            break
    return passages


def _phrase_count(passage: Passage, phrases: list[str]) -> int:
    heading = f"{passage.heading}\n{passage.heading_path}"
    return sum(1 for phrase in phrases if heading_has_phrase(heading, phrase))


def _on_printed_page(passage: Passage, page_number: int, kept: list[Passage]) -> bool:
    if not page_number:
        return False
    pages = {
        (item.policy_id, item.page)
        for item in kept
        if item.heading.lower().startswith(f"page {page_number} of")
    }
    return (passage.policy_id, passage.page) in pages


def _names_this(passage: Passage, phrases: list[str], page_number: int) -> bool:
    heading = f"{passage.heading}\n{passage.heading_path}"
    if any(heading_has_phrase(heading, phrase) for phrase in phrases):
        return True
    if page_number and passage.heading.lower().startswith(f"page {page_number} of"):
        return True
    return False


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
    distinctive = [token for token in set(token_list(query)) if len(token) >= 5 and token not in _GENERIC]

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
    one_policy = len({passage.title for passage in chosen}) == 1
    tied = len({round(passage.score, 2) for passage in chosen}) == 1
    if len(chosen) > MAX_PASSAGES and (tied or (one_policy and len({passage.page for passage in chosen}) <= 2)):
        return chosen[:16]
    return chosen[:MAX_PASSAGES]
