"""Extract tabular / text content from Excel, PDF, Word, and images."""

from __future__ import annotations

import base64
import csv
import io
import re
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".csv",
    ".pdf",
    ".docx",
    ".doc",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".webp",
    ".bmp",
}

# Encoded vision payload soft cap (~OpenAI practical limit for desk use).
_VISION_MAX_BYTES = 3_500_000


def detect_kind(filename: str, content_type: str | None = None) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".xlsx", ".xls", ".csv"}:
        return "excel"
    if ext == ".pdf":
        return "pdf"
    if ext in {".docx", ".doc"}:
        return "word"
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}:
        return "image"
    ct = (content_type or "").lower()
    if "spreadsheet" in ct or "excel" in ct or "csv" in ct:
        return "excel"
    if "pdf" in ct:
        return "pdf"
    if "word" in ct or "officedocument.wordprocessing" in ct:
        return "word"
    if ct.startswith("image/"):
        return "image"
    return "unknown"


def extract_document(path: Path, *, filename: str, content_type: str | None = None) -> dict[str, Any]:
    kind = detect_kind(filename, content_type)
    if kind == "excel":
        return _extract_excel(path, filename)
    if kind == "pdf":
        return _extract_pdf(path)
    if kind == "word":
        return _extract_word(path)
    if kind == "image":
        return _extract_image(path)
    raise ValueError(f"Unsupported file type: {filename}")


def _extract_excel(path: Path, filename: str) -> dict[str, Any]:
    ext = path.suffix.lower()
    if ext == ".csv":
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = [list(r) for r in reader]
        return _tabular_payload("excel", rows, sheet_name="csv")

    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    sheet = wb.active
    rows: list[list[Any]] = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(["" if c is None else c for c in row])
    wb.close()
    return _tabular_payload("excel", rows, sheet_name=sheet.title)


def _extract_pdf(path: Path) -> dict[str, Any]:
    import pdfplumber

    pages_text: list[str] = []
    tables: list[list[list[Any]]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:20]:
            text = (page.extract_text() or "").strip()
            if text:
                pages_text.append(text)
            for table in page.extract_tables() or []:
                cleaned = [[("" if c is None else str(c)).strip() for c in row] for row in table]
                if cleaned:
                    tables.append(cleaned)

    if tables:
        best = max(tables, key=lambda t: sum(1 for r in t for c in r if str(c).strip()))
        payload = _tabular_payload("pdf", best, sheet_name="pdf_table")
        payload["pages_text"] = pages_text[:5]
        return payload

    lines = []
    for block in pages_text:
        for line in block.splitlines():
            line = line.strip()
            if line:
                lines.append([line])
    if lines:
        # Prefer key:value style lines as a one-row record when it looks structured.
        kv = _lines_to_kv_row(lines)
        if kv:
            cols = list(kv.keys())
            return {
                "kind": "pdf",
                "sheet_name": "pdf_kv",
                "columns": cols,
                "rows": [kv],
                "sample_rows": [kv],
                "row_count": 1,
                "pages_text": pages_text[:5],
                "notes": "PDF text parsed as key/value fields.",
            }
        return _tabular_payload("pdf", [["text"], *lines], sheet_name="pdf_text")

    # Scanned PDF — render first pages for vision.
    try:
        images = _render_pdf_pages(path, max_pages=2)
        primary = images[0]
        return {
            "kind": "pdf",
            "columns": [],
            "rows": [],
            "sample_rows": [],
            "row_count": 0,
            "pages_text": [],
            "notes": f"Scanned PDF — {len(images)} page(s) prepared for vision analysis.",
            "needs_vision": True,
            "file_b64": primary["b64"],
            "mime": primary["mime"],
            "extra_images": images[1:],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "pdf",
            "columns": ["text"],
            "rows": [],
            "sample_rows": [],
            "row_count": 0,
            "pages_text": [],
            "notes": f"No extractable text and vision render failed: {exc}",
            "needs_vision": False,
        }


def _extract_word(path: Path) -> dict[str, Any]:
    from docx import Document

    doc = Document(path)
    rows: list[list[Any]] = []
    for table in doc.tables:
        for tr in table.rows:
            rows.append([(c.text or "").strip() for c in tr.cells])
        if rows:
            return _tabular_payload("word", rows, sheet_name="word_table")

    paras = [(p.text or "").strip() for p in doc.paragraphs if (p.text or "").strip()]
    if not paras:
        return {
            "kind": "word",
            "columns": ["text"],
            "rows": [],
            "sample_rows": [],
            "row_count": 0,
            "notes": "Empty Word document.",
        }

    kv = _lines_to_kv_row([[p] for p in paras])
    if kv and len(kv) >= 2:
        cols = list(kv.keys())
        return {
            "kind": "word",
            "sheet_name": "word_kv",
            "columns": cols,
            "rows": [kv],
            "sample_rows": [kv],
            "row_count": 1,
            "notes": "Word paragraphs parsed as key/value fields.",
        }
    return _tabular_payload("word", [["text"], *[[p] for p in paras]], sheet_name="word_text")


def _extract_image(path: Path) -> dict[str, Any]:
    prepared = _prepare_image_for_vision(path)
    return {
        "kind": "image",
        "columns": [],
        "rows": [],
        "sample_rows": [],
        "row_count": 0,
        "needs_vision": True,
        "file_b64": prepared["b64"],
        "mime": prepared["mime"],
        "notes": (
            "Scanned image prepared for high-detail AI vision "
            f"({prepared.get('width')}x{prepared.get('height')}, {prepared.get('bytes')} bytes)."
        ),
    }


def _prepare_image_for_vision(path: Path) -> dict[str, Any]:
    """Normalize/compress image for OpenAI vision (prefer readable JPEG under size cap)."""
    try:
        from PIL import Image, ImageOps, ImageEnhance
    except ImportError:
        raw = path.read_bytes()
        if len(raw) > _VISION_MAX_BYTES:
            raise ValueError(
                f"Image exceeds {_VISION_MAX_BYTES // (1024 * 1024)}MB and Pillow is unavailable to compress it."
            )
        suffix = path.suffix.lower().lstrip(".") or "png"
        mime = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "tif": "image/tiff",
            "tiff": "image/tiff",
            "bmp": "image/bmp",
        }.get(suffix, "image/png")
        return {"b64": base64.b64encode(raw).decode("ascii"), "mime": mime, "bytes": len(raw), "width": None, "height": None}

    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in {"RGB", "L"}:
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    # Mild contrast boost helps OCR-like table recovery on washed scans.
    try:
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.1)
    except Exception:  # noqa: BLE001
        pass

    max_side = 2048
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

    quality = 85
    payload = b""
    for q in (85, 75, 65, 55):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        payload = buf.getvalue()
        quality = q
        if len(payload) <= _VISION_MAX_BYTES:
            break
    if len(payload) > _VISION_MAX_BYTES:
        # Last resort: shrink further.
        shrink = 0.75
        while len(payload) > _VISION_MAX_BYTES and shrink > 0.35:
            nw, nh = max(1, int(img.size[0] * shrink)), max(1, int(img.size[1] * shrink))
            small = img.resize((nw, nh), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            small.save(buf, format="JPEG", quality=60, optimize=True)
            payload = buf.getvalue()
            img = small
            shrink -= 0.1
    if len(payload) > _VISION_MAX_BYTES:
        raise ValueError("Could not compress image enough for vision analysis.")

    return {
        "b64": base64.b64encode(payload).decode("ascii"),
        "mime": "image/jpeg",
        "bytes": len(payload),
        "width": img.size[0],
        "height": img.size[1],
        "jpeg_quality": quality,
    }


def _render_pdf_pages(path: Path, *, max_pages: int = 2) -> list[dict[str, Any]]:
    import fitz

    doc = fitz.open(path)
    out: list[dict[str, Any]] = []
    try:
        for i in range(min(max_pages, doc.page_count)):
            page = doc.load_page(i)
            # Higher DPI than before for clearer table glyphs.
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            png_bytes = pix.tobytes("png")
            # Re-encode via image prep for size control.
            tmp = path.parent / f".vision_page_{i}.png"
            try:
                tmp.write_bytes(png_bytes)
                prepared = _prepare_image_for_vision(tmp)
            finally:
                tmp.unlink(missing_ok=True)
            out.append(prepared)
    finally:
        doc.close()
    if not out:
        raise ValueError("PDF has no pages to render.")
    return out


def _lines_to_kv_row(lines: list[list[Any]]) -> dict[str, str] | None:
    data: dict[str, str] = {}
    for row in lines:
        text = " ".join(str(c).strip() for c in row if str(c).strip())
        if not text:
            continue
        m = re.match(r"^(.{2,60}?)\s*[:\-–]\s*(.+)$", text)
        if not m:
            continue
        key = _normalize_header(m.group(1), len(data))
        data[key] = m.group(2).strip()[:240]
        if len(data) >= 20:
            break
    return data if len(data) >= 2 else None


def _tabular_payload(kind: str, matrix: list[list[Any]], *, sheet_name: str) -> dict[str, Any]:
    if not matrix:
        return {
            "kind": kind,
            "sheet_name": sheet_name,
            "columns": [],
            "rows": [],
            "sample_rows": [],
            "row_count": 0,
        }

    header_idx = 0
    for i, row in enumerate(matrix[:10]):
        if any(str(c).strip() for c in row):
            header_idx = i
            break

    headers = [_normalize_header(c, i) for i, c in enumerate(matrix[header_idx])]
    body = matrix[header_idx + 1 :]
    records: list[dict[str, Any]] = []
    for row in body:
        if not any(str(c).strip() for c in row):
            records.append({h: "" for h in headers})
            continue
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        records.append({headers[i]: _cell(padded[i]) for i in range(len(headers))})

    return {
        "kind": kind,
        "sheet_name": sheet_name,
        "columns": headers,
        "rows": records,
        "sample_rows": records[:15],
        "row_count": len(records),
    }


def _normalize_header(value: Any, index: int) -> str:
    text = str(value or "").strip()
    if not text:
        return f"col_{index + 1}"
    text = re.sub(r"\s+", " ", text)
    return text[:80]


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return value.strip()
    return value
