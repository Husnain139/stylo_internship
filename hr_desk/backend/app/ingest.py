"""Read policy files and split them on headings."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from io import BytesIO
from pathlib import Path

from .access import AUDIENCES
from .config import BACKEND_ROOT
from .models import ChunkDraft, PolicyDraft

POLICY_DIR = BACKEND_ROOT / "data" / "policies"
CHUNK_CHARS = 3200
CHUNK_OVERLAP = 400
_OFFICE_SUFFIXES = (".pdf", ".docx")
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_policy_text(raw: str, policy_id: str | None = None) -> PolicyDraft:
    if not raw.startswith("---"):
        raise ValueError("A policy file needs a title block at the top.")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError("A policy file needs a title block at the top.")
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    title = meta.get("title", "").strip()
    audience = meta.get("audience", "").strip()
    if not title:
        raise ValueError("Give this policy a name.")
    if audience not in AUDIENCES:
        raise ValueError("Choose who can see this policy.")
    try:
        effective_from = date.fromisoformat(meta["effective_from"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Choose the date this policy starts.") from exc
    effective_to_raw = meta.get("effective_to", "")
    effective_to = date.fromisoformat(effective_to_raw) if effective_to_raw else None
    body = parts[2].strip()
    if not body:
        raise ValueError("Add the policy text or choose a file.")
    if not policy_id:
        policy_id = "sample-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    sample = meta.get("sample", "true").lower() != "false"
    return PolicyDraft(
        id=policy_id,
        title=title,
        audience=audience,
        effective_from=effective_from,
        effective_to=effective_to,
        sample=sample,
        body=body,
    )


def load_office_policies() -> list[PolicyDraft]:
    """Real PDF and Word files placed in the policies folder by HR."""
    policies, _skipped = read_office_policies()
    return policies


def read_office_policies() -> tuple[list[PolicyDraft], list[str]]:
    """Return readable policies and the file names that had no text layer."""
    policies = []
    skipped: list[str] = []
    paths = [
        path
        for path in sorted(POLICY_DIR.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in _OFFICE_SUFFIXES
    ]
    for path in paths:
        payload = path.read_bytes()
        body = read_upload(path.name, payload)
        if not body or not _text_layer_usable(path, body):
            skipped.append(path.name)
            continue
        policies.append(
            PolicyDraft(
                id="doc-" + hashlib.sha256(path.name.encode("utf-8") + b"\0" + payload).hexdigest()[:16],
                title=_office_title(path),
                audience="everyone",
                effective_from=_office_date(path),
                effective_to=None,
                sample=False,
                body=body,
            )
        )
    return policies, skipped


def _text_layer_usable(path: Path, body: str) -> bool:
    """An Urdu scan can expose only a short English header. That is not the policy."""
    name_is_urdu = any("\u0600" <= ch <= "\u06ff" for ch in path.name)
    if not name_is_urdu:
        return True
    return any(
        "\u0600" <= ch <= "\u06ff"
        or "\u0750" <= ch <= "\u077f"
        or "\ufb50" <= ch <= "\ufdff"
        or "\ufe70" <= ch <= "\ufeff"
        for ch in body
    )


def _office_title(path: Path) -> str:
    stem = re.sub(r"^\d+\.\s*", "", path.stem)
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = re.sub(r"\s+\d{6}$", "", stem)
    stem = re.sub(r"\s+[A-Za-z]{3,9}-\d{4}$", "", stem)
    stem = re.sub(r"\s+FINAL$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+-\s+Stylo$", "", stem, flags=re.IGNORECASE)
    return stem.strip(" -–") or path.stem


def _office_date(path: Path) -> date:
    name = path.stem
    numbered = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", name)
    if numbered:
        day, month, year = (int(numbered.group(1)), int(numbered.group(2)), 2000 + int(numbered.group(3)))
        try:
            return date(year, month, day)
        except ValueError:
            pass
    named = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*-(\d{4})", name, re.IGNORECASE)
    if named:
        return date(int(named.group(2)), _MONTHS[named.group(1)[:3].lower()], 1)
    return date(2025, 1, 1)


def _sections(body: str) -> list[tuple[str, str]]:
    heading = ""
    buffer: list[str] = []
    found: list[tuple[str, str]] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            found.append((heading, text))

    for line in body.splitlines():
        if line.startswith("## "):
            flush()
            buffer = []
            heading = line[3:].strip()
        else:
            buffer.append(line)
    flush()
    if found:
        return found
    text = body.strip()
    return [("", text)] if text else []


def _windows(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end == len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
        if start >= end:
            break
    return parts


def make_chunks(policy: PolicyDraft) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    for heading, text in _sections(policy.body):
        label = f"{policy.title}, {heading}" if heading else policy.title
        for piece in _windows(text):
            embed_text = "\n".join(part for part in (policy.title, heading, piece) if part)
            chunks.append(
                ChunkDraft(
                    section_label=label,
                    heading=heading or policy.title,
                    body=piece,
                    embed_text=embed_text,
                )
            )
    return chunks


def read_upload(filename: str, payload: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(payload))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if name.endswith(".docx"):
        return _docx_text(payload)
    return payload.decode("utf-8", errors="replace").strip()


def _docx_text(payload: bytes) -> str:
    from docx import Document

    document = Document(BytesIO(payload))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts).strip()
