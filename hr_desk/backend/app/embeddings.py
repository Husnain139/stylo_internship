"""Vector math for the in-memory checks. The live app embeds with OpenAI."""

from __future__ import annotations

import math


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)
