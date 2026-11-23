"""Render the source page behind a passage so the policy text can show it."""

from __future__ import annotations

from pathlib import Path

from .config import DATA_ROOT

_MEDIA = DATA_ROOT / "policy_media"


def source_page_url(passage) -> str:
    """A picture of the PDF or Word page this passage was read from."""
    source = _source_file(getattr(passage, "policy_id", ""))
    if source is None:
        return ""
    policy_id = passage.policy_id
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        page = getattr(passage, "page", None) or 0
        if page < 1:
            return ""
        return _url(policy_id, _render(source, page - 1, policy_id))
    if suffix == ".docx":
        pdf = _docx_pdf(source, policy_id)
        if pdf is None:
            return ""
        index = _find_page(pdf, getattr(passage, "heading", ""), getattr(passage, "body", ""))
        if index is None:
            return ""
        return _url(policy_id, _render(pdf, index, policy_id))
    return ""


def _source_file(policy_id: str) -> Path | None:
    if not policy_id:
        return None
    from .ingest import find_policy_file

    return find_policy_file(policy_id)


def _url(policy_id: str, name: str) -> str:
    if not name:
        return ""
    return f"/api/media/{policy_id}/{name}"


def _render(pdf: Path, index: int, policy_id: str) -> str:
    import pymupdf

    name = f"page-{index + 1}.png"
    folder = _MEDIA / policy_id
    target = folder / name
    if target.is_file():
        return name
    document = pymupdf.open(pdf)
    try:
        if index < 0 or index >= document.page_count:
            return ""
        page = document[index]
        longest = max(page.rect.width, page.rect.height)
        if longest <= 0:
            return ""
        scale = min(1.2, 2000 / longest)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        folder.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pix.tobytes("png"))
    finally:
        document.close()
    return name


def _find_page(pdf: Path, heading: str, body: str) -> int | None:
    import pymupdf

    heading_needle = " ".join((heading or "").split()).lower()
    body_needle = " ".join((body or "").split()).lower()[:80]
    document = pymupdf.open(pdf)
    try:
        pages = [" ".join(page.get_text("text").split()).lower() for page in document]
    finally:
        document.close()
    if len(body_needle) >= 24:
        for index, text in enumerate(pages):
            if body_needle in text:
                return index
    if len(heading_needle) < 8:
        return None
    hits = [index for index, text in enumerate(pages) if heading_needle in text]
    if len(hits) == 1:
        return hits[0]
    deeper = [index for index in hits if pages[index].find(heading_needle) > 80]
    if deeper:
        return deeper[0]
    return hits[0] if hits else None


def _docx_pdf(docx: Path, policy_id: str) -> Path | None:
    target = _MEDIA / policy_id / "source.pdf"
    if target.is_file() and target.stat().st_mtime >= docx.stat().st_mtime:
        return target
    return None
