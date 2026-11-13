"""Small model for a direct policy question. Larger small model when the question is harder."""

from __future__ import annotations

from .config import model_mini, model_nano
from .models import Passage

_COMPLEX = (
    "compare",
    "difference",
    "versus",
    " vs ",
    "exception",
    "conflict",
    "what if",
    "disagree",
)


def choose_model(question: str, passages: list[Passage]) -> str:
    folded = f" {question.lower()} "
    titles = {passage.title for passage in passages}
    if len(question) > 400 or len(titles) >= 3:
        return model_mini()
    if any(word in folded for word in _COMPLEX):
        return model_mini()
    return model_nano()
