"""Turn a follow-up into one search question, and drop history on a topic change."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import HISTORY_TURNS
from .textutil import token_set

_FOLLOW = re.compile(r"(?i)^(?:what|how) about\s+(.+?)\s*\??$")


@dataclass(frozen=True)
class Rewrite:
    search_query: str
    background: str
    note: str
    needs_model: bool = False


def recent_history(history: list[dict], limit: int = HISTORY_TURNS) -> list[dict]:
    cleaned = []
    for turn in history or []:
        role = turn.get("role")
        text = (turn.get("text") or "").strip()
        if role in {"user", "assistant"} and text:
            cleaned.append({"role": role, "text": text[:1000]})
    return cleaned[-limit:]


def _last_user_question(history: list[dict]) -> str:
    for turn in reversed(history):
        if turn["role"] == "user":
            return turn["text"]
    return ""


def rewrite_question(question: str, history: list[dict]) -> Rewrite:
    """Rules cover the common cases. needs_model means a cheap model should rewrite."""
    text = question.strip()
    turns = recent_history(history)
    prior = _last_user_question(turns)
    follow = _FOLLOW.match(text)
    if follow and prior:
        topic = follow.group(1).strip()
        shared = token_set(topic) & token_set(prior)
        if shared:
            return Rewrite(topic, prior, "follow-up")
        return Rewrite(topic, "", "topic-change")
    words = re.findall(r"[A-Za-z0-9']+", text)
    if len(words) >= 4:
        note = "topic-change" if prior else "no-history"
        return Rewrite(text, "", note)
    if not prior:
        return Rewrite(text, "", "no-history")
    return Rewrite(text, prior, "model", needs_model=True)
