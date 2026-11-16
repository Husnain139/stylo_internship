"""Read policy files and split them on headings."""

from __future__ import annotations

import re
import shutil
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from .config import BACKEND_ROOT
from .models import ChunkDraft, PolicyDraft

POLICY_DIR = BACKEND_ROOT / "data" / "policies"
CHUNK_CHARS = 3200
CHUNK_OVERLAP = 400
_OFFICE_SUFFIXES = (".pdf", ".docx")


def load_office_policies() -> list[PolicyDraft]:
    """Real PDF and Word files placed in the policies folder by HR."""
    from .passages import office_policy

    if not POLICY_DIR.exists():
        return []
    policies = []
    paths = [
        path
        for path in sorted(POLICY_DIR.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in _OFFICE_SUFFIXES
    ]
    for path in paths:
        policy = office_policy(path)
        if policy is None or not policy.chunks:
            continue
        policies.append(policy)
    return policies


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
        import pymupdf

        document = pymupdf.open(stream=payload, filetype="pdf")
        try:
            return "\n".join(page.get_text("text") or "" for page in document).strip()
        finally:
            document.close()
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


def folder_filenames() -> dict[str, str]:
    """Map each folder policy id to the file name currently on disk."""
    if not POLICY_DIR.exists():
        return {}
    from .passages import file_policy_id

    found: dict[str, str] = {}
    for path in POLICY_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in _OFFICE_SUFFIXES:
            continue
        found[file_policy_id(path.name, path.read_bytes())] = path.name
    return found


def find_policy_file(policy_id: str) -> Path | None:
    """The folder file whose hash is this id, if the policy was read from disk."""
    if not policy_id.startswith("doc-") or not POLICY_DIR.exists():
        return None
    from .passages import file_policy_id

    for path in POLICY_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in _OFFICE_SUFFIXES:
            continue
        if file_policy_id(path.name, path.read_bytes()) == policy_id:
            return path
    return None


def remove_policy_files(
    policy_id: str,
    keep_file: Path | None = None,
    keep_media: bool = False,
) -> None:
    """Drop the source file and saved pictures so a restart cannot bring the policy back."""
    source = find_policy_file(policy_id)
    if source is not None and _inside(source, POLICY_DIR):
        if keep_file is None or source.resolve() != keep_file.resolve():
            source.unlink()
    if keep_media:
        return
    media = BACKEND_ROOT / "data" / "policy_media" / policy_id
    if media.exists() and _inside(media, BACKEND_ROOT / "data" / "policy_media"):
        shutil.rmtree(media)


def replacement_policy(
    title: str,
    audience: str,
    effective_from: date,
    text: str,
    filename: str,
    payload: bytes,
    previous: Path | None,
) -> tuple[PolicyDraft, Path | None]:
    """Build the policy that replaces an old one. PDF and Word keep the full reader."""
    suffix = Path(filename).suffix.lower() if filename else ""
    if payload and suffix in _OFFICE_SUFFIXES:
        from .passages import policy_from_bytes

        stored_name = _destination_name(filename, previous)
        try:
            policy = policy_from_bytes(stored_name, payload)
        except Exception as exc:
            raise ValueError("unreadable") from exc
        if policy is None or not policy.chunks:
            raise ValueError("unreadable")
        _retitle(policy, title, audience, effective_from)
        policy.source_name = stored_name
        return policy, POLICY_DIR / stored_name
    body = text.strip()
    if payload and filename:
        body = read_upload(filename, payload).strip()
    if not body:
        raise ValueError("empty")
    policy = PolicyDraft(
        id="upload-" + uuid4().hex[:16],
        title=title,
        audience=audience,
        effective_from=effective_from,
        effective_to=None,
        body=body,
        source_name=Path(filename).name if filename else "",
    )
    policy.chunks = make_chunks(policy)
    return policy, None


def write_policy_file(path: Path, payload: bytes) -> None:
    if not _inside(path, POLICY_DIR):
        raise ValueError("outside")
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _retitle(policy: PolicyDraft, title: str, audience: str, effective_from: date) -> None:
    old = policy.title
    policy.title = title
    policy.audience = audience
    policy.effective_from = effective_from
    policy.effective_to = None
    for chunk in policy.chunks or []:
        if old and (chunk.section_label == old or chunk.section_label.startswith(old + ", ")):
            chunk.section_label = title + chunk.section_label[len(old) :]
        lines = chunk.embed_text.split("\n")
        if lines and lines[0] == old:
            lines[0] = title
            chunk.embed_text = "\n".join(lines)


def _destination_name(filename: str, previous: Path | None) -> str:
    safe = _safe_filename(filename)
    if previous is not None and previous.name == safe:
        return safe
    if not (POLICY_DIR / safe).exists():
        return safe
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    return f"{stem}-{uuid4().hex[:8]}{suffix}"


def _safe_filename(name: str) -> str:
    base = Path(name or "").name
    suffix = Path(base).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        suffix = ".pdf"
    stem = re.sub(r"[^A-Za-z0-9._ ()-]+", "", Path(base).stem).strip().strip(".")
    if not stem:
        stem = "policy"
    return f"{stem[:80]}{suffix}"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
