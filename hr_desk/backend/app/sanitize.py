"""Remove leaked ids, invented links, and numbers that are not in the passages."""

from __future__ import annotations

import re

from .config import CANARY, REFUSAL, UNKNOWN

_CHUNK = re.compile(
    r"\[/?chunk_[^\]]+\]|chunk_\d+_doc_\d+|\[doc_\d+\]|\bdoc_\d+\b",
    re.I,
)
_URL = re.compile(r"https?://[^\s)>\]]+")
_NUMBER = re.compile(r"\d+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _allowed_urls(passages: list[str]) -> set[str]:
    found = set()
    for text in passages:
        for match in _URL.findall(text):
            found.add(match.rstrip(".,"))
    return found


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


def sanitize(answer: str, passage_texts: list[str], allowed_numbers_from: str = "") -> str:
    if not answer or not answer.strip():
        return UNKNOWN
    if CANARY in answer or "Internal marker" in answer:
        return REFUSAL
    allowed_urls = _allowed_urls(passage_texts)

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,")
        if url in allowed_urls:
            return match.group(0)
        return ""

    cleaned = _URL.sub(replace_url, answer)
    cleaned = _CHUNK.sub("", cleaned)
    allowed_numbers = set(_NUMBER.findall(" ".join(passage_texts) + " " + allowed_numbers_from))
    kept = []
    for sentence in _sentences(cleaned):
        numbers = _NUMBER.findall(sentence)
        if any(number not in allowed_numbers for number in numbers):
            continue
        letters = re.sub(r"[^A-Za-z0-9]", "", sentence)
        if len(letters) < 8:
            continue
        kept.append(sentence)
    text = " ".join(kept)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([.,!?])", r"\1", text).strip()
    return text or UNKNOWN
