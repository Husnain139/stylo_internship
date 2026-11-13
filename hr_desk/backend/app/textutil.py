"""Token helpers shared by search, embeddings, and number checks."""

from __future__ import annotations

import re

STOP = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "do",
    "does",
    "did",
    "i",
    "me",
    "my",
    "we",
    "our",
    "you",
    "your",
    "how",
    "many",
    "what",
    "when",
    "where",
    "who",
    "why",
    "can",
    "get",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "please",
    "about",
    "this",
    "that",
    "with",
    "from",
    "each",
    "per",
    "it",
    "be",
    "if",
    "as",
    "at",
    "by",
    "tell",
    "stylo",
    "policy",
    "policies",
}


def token_list(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if word not in STOP and len(word) > 1]


def token_set(text: str) -> set[str]:
    return set(token_list(text))


def keyword_score(query: str, passage: str) -> float:
    wanted = token_set(query)
    if not wanted:
        return 0.0
    found = token_set(passage)
    return len(wanted & found) / len(wanted)


def normalize_for_rules(text: str) -> str:
    cleaned = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    cleaned = re.sub(r"'s\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
