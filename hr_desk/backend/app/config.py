"""Shared settings. One place for the cost limits."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DESK_ROOT = BACKEND_ROOT.parent

MAX_USER_CHARS = 1000
CLASSIFIER_MAX_TOKENS = 30
REWRITE_MAX_TOKENS = 120
ANSWER_MAX_TOKENS_NANO = 400
ANSWER_MAX_TOKENS_MINI = 700
TEMPERATURE_ANSWER = 0.1
TEMPERATURE_CLASSIFIER = 0.0
TIMEOUT_CLASSIFIER_S = 8.0
TIMEOUT_ANSWER_S = 20.0
TIMEOUT_MODERATION_S = 8.0
CACHE_SIMILARITY = 0.92
RETRIEVE_TOP_K = 6
RETRIEVE_CANDIDATES = 20
MIN_VECTOR_SCORE = 0.25
HISTORY_TURNS = 6
PASSAGE_SCORE_WINDOW = 0.12
MAX_PASSAGES = 4

CANARY = "STYLO-PROMPT-DO-NOT-REPEAT"

REFUSAL = "I can't answer that."
ROLE_REFUSAL = "I can't answer that. Your role doesn't include this."
UNKNOWN = "I couldn't find this in the policies I can open. Ask HR."
TOO_LONG = "Please ask a shorter question."
EMPTY_QUESTION = "Type a question first."
UNAVAILABLE = "The assistant is not available right now. Try again in a moment."


def model_nano() -> str:
    return os.environ.get("HR_DESK_MODEL_NANO", "gpt-5-nano").strip() or "gpt-5-nano"


def model_mini() -> str:
    return os.environ.get("HR_DESK_MODEL_MINI", "gpt-5-mini").strip() or "gpt-5-mini"


def embed_model() -> str:
    return os.environ.get("HR_DESK_EMBED_MODEL", "text-embedding-3-small").strip() or "text-embedding-3-small"


def openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def answer_max_tokens(model: str) -> int:
    if model == model_mini():
        return ANSWER_MAX_TOKENS_MINI
    return ANSWER_MAX_TOKENS_NANO
