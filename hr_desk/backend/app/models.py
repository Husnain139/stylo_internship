"""Records that move through the ask pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Employee:
    email: str
    name: str
    designation: str


@dataclass
class PolicyDraft:
    id: str
    title: str
    audience: str
    effective_from: date
    effective_to: date | None
    sample: bool
    body: str


@dataclass
class ChunkDraft:
    section_label: str
    heading: str
    body: str
    embed_text: str


@dataclass
class Passage:
    id: str
    policy_id: str
    title: str
    section_label: str
    heading: str
    body: str
    audience: str
    effective_from: date
    effective_to: date | None
    vec_score: float = 0.0
    kw_score: float = 0.0
    score: float = 0.0


@dataclass(frozen=True)
class Citation:
    label: str
    text: str


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


@dataclass
class TraceRecord:
    id: str
    created_at: str
    email: str
    name: str
    designation: str
    question: str
    guardrail: str
    guardrail_reason: str
    classifier_called: bool
    cache: str
    rewritten_question: str
    history_note: str
    search: str
    sections: list[str] = field(default_factory=list)
    withheld: bool = False
    scores: list[dict] = field(default_factory=list)
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    outcome: str = ""
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    prompt_version: str = ""


@dataclass
class AskResult:
    answer: str
    outcome: str
    citations: list[Citation]
    trace_id: str
