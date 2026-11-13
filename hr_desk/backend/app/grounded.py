"""A grounded answer from the passages, used when no model call is wanted."""

from __future__ import annotations

import re

from .models import Passage
from .textutil import token_set


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def draft_from_passages(question: str, passages: list[Passage]) -> str:
    if not passages:
        return ""
    wanted = token_set(question)
    ranked: list[tuple[int, str]] = []
    for passage in passages:
        for sentence in _sentences(passage.body):
            overlap = len(wanted & token_set(sentence))
            if overlap:
                ranked.append((overlap, sentence))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return _sentences(passages[0].body)[0]
    picked: list[str] = []
    for _, sentence in ranked:
        if sentence not in picked:
            picked.append(sentence)
        if len(picked) == 2:
            break
    return " ".join(picked)
