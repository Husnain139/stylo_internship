"""Read PDF pages with PyMuPDF and pdfplumber. Writes synthetic sample PDFs."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pymupdf


def read_pages(path: Path) -> list[tuple[int, str]]:
    doc = pymupdf.open(path)
    pages: list[list] = []
    try:
        if doc.page_count < 1:
            raise ValueError("PDF has no pages")
        for index, page in enumerate(doc, start=1):
            pages.append([index, page.get_text("text") or ""])
    finally:
        doc.close()

    try:
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                lines: list[str] = []
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [cell.strip() for cell in row if cell and str(cell).strip()]
                        if cells:
                            lines.append(" | ".join(cells))
                if not lines or index > len(pages):
                    continue
                extra = "\n".join(lines)
                if extra not in pages[index - 1][1]:
                    pages[index - 1][1] = pages[index - 1][1] + "\n" + extra
    except Exception:
        # Text from PyMuPDF is enough when the file has no recoverable tables.
        pass

    return [(number, text) for number, text in pages]


def write_sample_pdf(path: Path, page_texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    try:
        for text in page_texts:
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), text, fontsize=12, fontname="helv")
        doc.save(path)
    finally:
        doc.close()


def _render_text_pixmaps(page_texts: list[str], *, dpi: int = 144) -> list[pymupdf.Pixmap]:
    """Draw text pages then rasterize — used for scanned/OCR fixtures."""
    source = pymupdf.open()
    pixmaps: list[pymupdf.Pixmap] = []
    try:
        for text in page_texts:
            page = source.new_page(width=595, height=842)
            page.draw_rect(page.rect, color=(0.93, 0.93, 0.94), fill=(0.93, 0.93, 0.94))
            page.insert_text((72, 72), text, fontsize=12, fontname="helv", color=(0.08, 0.08, 0.1))
        matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
        for page in source:
            pixmaps.append(page.get_pixmap(matrix=matrix, alpha=False))
    finally:
        source.close()
    return pixmaps


def write_scanned_pdf(path: Path, page_texts: list[str], *, dpi: int = 144) -> None:
    """Image-only PDF (no text layer). Good for local OCR / empty-extract tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmaps = _render_text_pixmaps(page_texts, dpi=dpi)
    doc = pymupdf.open()
    try:
        for pixmap in pixmaps:
            page = doc.new_page(width=595, height=842)
            page.insert_image(page.rect, pixmap=pixmap)
        doc.save(path)
    finally:
        doc.close()


def write_scan_png(path: Path, page_text: str, *, dpi: int = 144) -> None:
    """Single-page PNG scan for OCR tooling outside the PDF uploader."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = _render_text_pixmaps([page_text], dpi=dpi)[0]
    pixmap.save(str(path))
