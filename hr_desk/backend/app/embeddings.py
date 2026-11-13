"""Embeddings. The fake embedder keeps tests and offline runs deterministic."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from .config import EMBED_DIM
from .textutil import token_list


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


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


class FakeEmbedder:
    """Hash tokens into a unit vector so shared words land near each other."""

    dim = EMBED_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = token_list(text)
        features = list(tokens)
        features.extend(f"{a}_{b}" for a, b in zip(tokens, tokens[1:]))
        for feature in features:
            digest = hashlib.sha256(feature.encode()).digest()
            for offset in range(0, 12, 2):
                index = int.from_bytes(digest[offset : offset + 2], "little") % self.dim
                sign = 1.0 if digest[offset + 1] % 2 == 0 else -1.0
                vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
