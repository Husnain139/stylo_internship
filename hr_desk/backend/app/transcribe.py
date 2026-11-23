"""Turn a policy picture into the words that search and the answer model can read."""

from __future__ import annotations

import hashlib
import os

from .config import DATA_ROOT, openai_api_key

_CACHE = DATA_ROOT / "transcriptions"

def transcribe_picture(image: bytes) -> str:
    digest = hashlib.sha256(image).hexdigest()
    cached = _CACHE / f"{digest}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip()
    text = _local_ocr(image)
    if not text and _vision_enabled() and len(image) <= 2 * 1024 * 1024:
        text = _vision(image)
    if text:
        _CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8")
    return text


def _local_ocr(image: bytes) -> str:
    import pymupdf

    if not image.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        return ""
    try:
        with pymupdf.open(stream=image) as document:
            page = document[0]
            dpi = min(150, int(1800 * 72 / max(page.rect.width, page.rect.height, 1)))
            if dpi < 36:
                return ""
            text_page = page.get_textpage_ocr(language="eng", dpi=dpi, full=True)
            return page.get_text("text", textpage=text_page).strip()
    except (RuntimeError, ValueError):
        return ""


def _vision_enabled() -> bool:
    return os.environ.get("HR_DESK_VISION", "").strip() == "1" and bool(openai_api_key())


def _vision(image: bytes) -> str:
    import base64

    from openai import OpenAI

    from .config import model_nano

    encoded = base64.b64encode(image).decode("ascii")
    try:
        response = OpenAI(api_key=openai_api_key(), max_retries=0, timeout=12).chat.completions.create(
            model=model_nano(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe this policy page into markdown. Use ## for headings. "
                                "Render every table as a markdown table with a header row. "
                                "List every form field. Skip logos and signatures. Do not invent text."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                    ],
                }
            ],
            max_completion_tokens=1200,
        )
    except Exception:
        return ""
    return (response.choices[0].message.content or "").strip()


def save_picture(policy_key: str, name: str, image: bytes) -> str:
    folder = DATA_ROOT / "policy_media" / policy_key
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        path.write_bytes(image)
    return f"{policy_key}/{name}"
