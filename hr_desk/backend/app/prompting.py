"""Build the prompts the answer model sees. Internal ids stay out."""

from __future__ import annotations

import hashlib
from datetime import date

from .config import BACKEND_ROOT, CANARY
from .models import Passage

_PROMPT_PATH = BACKEND_ROOT / "prompts" / "system.md"


def prompt_version() -> str:
    return hashlib.sha256(_PROMPT_PATH.read_bytes()).hexdigest()[:12]


def system_prompt(today: date) -> str:
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    if CANARY not in raw:
        raise RuntimeError("The system prompt is missing its leak marker.")
    return raw.replace("{{today}}", today.isoformat())


def user_message(question: str, background: str, passages: list[Passage]) -> str:
    blocks = []
    for passage in passages:
        end = ""
        if passage.effective_to:
            end = f" to {passage.effective_to.isoformat()}"
        blocks.append(
            "\n".join(
                [
                    f"Source: {passage.section_label}",
                    f"Effective: {passage.effective_from.isoformat()}{end}",
                    passage.body.strip(),
                ]
            )
        )
    background_line = background.strip() or "None"
    return (
        f"Background: {background_line}\n\n"
        "Passages:\n\n"
        + "\n\n".join(blocks)
        + f"\n\nQuestion: {question.strip()}"
    )
