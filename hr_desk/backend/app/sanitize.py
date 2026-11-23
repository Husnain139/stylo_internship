"""Remove leaked ids, invented links, and numbers that are not in the passages."""

from __future__ import annotations

import re

from .access import grade_band
from .config import CANARY, REFUSAL, UNKNOWN

_CHUNK = re.compile(
    r"\[/?chunk_[^\]]+\]|chunk_\d+_doc_\d+|\[doc_\d+\]|\bdoc_\d+\b",
    re.I,
)
_URL = re.compile(r"https?://[^\s)>\]]+")
_NUMBER = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)*")
_SENTENCE = re.compile(r"(?<!\bRs\.)(?<=[.!?])\s+", re.IGNORECASE)
_MONEY = re.compile(r"\b(?:rs\b|pkr\b|rupees?\b)", re.IGNORECASE)
_ECHO = re.compile(
    r"^(source\b|effective\b|source line\b|if you want\b|if the passage\b|next,\s|we would add\b)",
    re.I,
)


def _allowed_urls(passages: list[str]) -> set[str]:
    found = set()
    for text in passages:
        for match in _URL.findall(text):
            found.add(match.rstrip(".,"))
    return found


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


def _numbers(text: str) -> set[str]:
    return {token.replace(",", "") for token in _NUMBER.findall(text)}


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
    evidence = [(grade_band(passage), _numbers(passage)) for passage in passage_texts]
    allowed_numbers = _numbers(allowed_numbers_from).union(*(numbers for _, numbers in evidence))
    kept_lines: list[str] = []
    blank = False
    for raw_line in cleaned.replace("\r\n", "\n").split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            blank = True
            continue
        prefix = ""
        body = stripped
        bullet = re.match(r"^[-*•]\s+(.*)$", stripped)
        if bullet:
            prefix = "- "
            body = bullet.group(1).strip()
        kept = []
        for sentence in _sentences(body):
            numbers = _numbers(sentence)
            if not numbers <= allowed_numbers:
                continue
            if numbers and _MONEY.search(sentence):
                grade = grade_band(sentence)
                if not any(numbers <= values and (grade is None or grade == band) for band, values in evidence):
                    continue
            letters = re.sub(r"[^A-Za-z0-9]", "", sentence)
            if len(letters) < 8 or _ECHO.search(sentence):
                continue
            kept.append(sentence)
        if not kept:
            continue
        if blank and kept_lines:
            kept_lines.append("")
        blank = False
        kept_lines.append(prefix + " ".join(kept))
    text = "\n".join(kept_lines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([.,!?])", r"\1", text).strip()
    return text or UNKNOWN
