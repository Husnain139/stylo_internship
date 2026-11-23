"""Numbered headings and subheadings, such as 3.1 and 3.1.5."""

from __future__ import annotations

import re
from dataclasses import replace

_CLAUSE = re.compile(r"(?<!\d)(?<!\d\.)(\d+(?:\.\d+)+)\b")
_TITLE_SKIP = {"policy", "policies", "head", "office", "guidelines", "user", "action"}


_PHRASE_SKIP = _TITLE_SKIP | {
    "what", "when", "where", "which", "show", "tell", "give", "does", "about",
    "from", "with", "this", "that", "have", "your", "please", "title", "titles",
    "short", "brief", "summary", "point", "points", "section", "clause",
    "heading", "explain", "describe", "mean", "means",
}


def heading_has_phrase(heading: str, phrase: str) -> bool:
    """The heading contains these words in order, with small words allowed between them."""
    parts = re.findall(r"[a-z0-9]+", (phrase or "").lower())
    if not parts:
        return False
    pattern = r"\b" + r"\b.*\b".join(re.escape(part) for part in parts) + r"\b"
    return re.search(pattern, (heading or "").lower(), re.DOTALL) is not None


def heading_sql_pattern(phrase: str) -> str:
    """Postgres word-boundary form of heading_has_phrase."""
    parts = re.findall(r"[a-z0-9]+", (phrase or "").lower())
    if not parts:
        return ""
    return r"\m" + r"\M.*\m".join(re.escape(part) for part in parts) + r"\M"


def heading_phrases(question: str) -> list[str]:
    """Printed titles the question names, such as Annexure C or KM Coverage."""
    text = (question or "").lower()
    phrases: list[str] = []
    for match in re.finditer(r"annexure\s+[a-z0-9]+", text):
        phrases.append(match.group(0))
    words = [token for token in re.findall(r"[a-z0-9]+", text) if token not in _PHRASE_SKIP]
    if "annexures" in words:
        phrases.append("annexures")
    for index in range(len(words) - 1):
        left, right = words[index], words[index + 1]
        if (len(left) >= 2 and len(right) >= 4) or (len(left) >= 4 and len(right) >= 2):
            phrases.append(f"{left} {right}")
    if not phrases and len(words) == 1 and len(words[0]) >= 3:
        phrases.append(words[0])
    unique: list[str] = []
    for phrase in phrases:
        if phrase not in unique:
            unique.append(phrase)
    return unique[:6]


def asked_page(question: str) -> int:
    """The printed page number, when the question asks for one."""
    match = re.search(r"\bpage\s+(\d{1,2})\b", question or "", re.I)
    if not match:
        return 0
    number = int(match.group(1))
    return number if 1 <= number <= 40 else 0


def asked_clause(question: str) -> str:
    """The most specific heading number in the question. 3.1.5 wins over 3.1."""
    numbers = []
    for match in _CLAUSE.finditer(question or ""):
        number = match.group(1)
        if number not in numbers:
            numbers.append(number)
    if not numbers:
        return ""
    return max(numbers, key=lambda number: (number.count("."), len(number)))


def clause_regex(number: str) -> str:
    """Match this heading or its subheadings, not a longer sibling such as 3.1.50."""
    escaped = r"\.".join(re.escape(part) for part in number.split("."))
    return rf"(^|[^0-9.]){escaped}(\.|[^0-9.]|$)"


def contains_clause(text: str, number: str) -> bool:
    if not number:
        return False
    return re.search(clause_regex(number), text or "") is not None


def named_policy_titles(question: str, passages) -> set[str]:
    """Titles the person actually named. The word policy alone names none."""
    folded = (question or "").lower()
    matched = set()
    for title in {passage.title for passage in passages}:
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", title.lower())
            if len(word) >= 5 and word not in _TITLE_SKIP
        ]
        if any(word in folded for word in words):
            matched.add(title)
    return matched


def extract_clause(text: str, number: str) -> str:
    """The words of this heading, including its subheadings and not the next heading."""
    if not text or not number:
        return ""
    starts = list(_CLAUSE.finditer(text))
    if not starts:
        return ""
    pieces = []
    for index, match in enumerate(starts):
        found = match.group(1)
        if found != number and not found.startswith(number + "."):
            continue
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        piece = text[match.start() : end].strip()
        if piece:
            pieces.append(piece)
    return "\n".join(pieces).strip()


def focus_clauses(passages, question: str):
    """Keep only the numbered point. None means the question did not ask for one."""
    number = asked_clause(question)
    if not number:
        return None
    titles = named_policy_titles(question, passages)
    pool = [passage for passage in passages if passage.title in titles] if titles else list(passages)
    focused = []
    for passage in pool:
        body = extract_clause(f"{passage.heading}\n{passage.body}", number)
        if not body:
            continue
        focused.append(replace(passage, body=body))
    return focused
