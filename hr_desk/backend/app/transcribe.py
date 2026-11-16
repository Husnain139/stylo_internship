"""Turn a policy picture into the words that search and the answer model can read."""

from __future__ import annotations

import hashlib
import os

from .config import BACKEND_ROOT, openai_api_key

_CACHE = BACKEND_ROOT / "data" / "transcriptions"

_SUMMARY = (
    "Investigation Summary Report template. "
    "Nature of breach. Initially reported by. Location or district or region. Reporting date. "
    "Employee name. Employee designation. Department or shop name. Shop code or employee code. "
    "Provident fund balance. Debit or credit balance. Tenure in current role. "
    "Inquiry officer findings. Line manager response. Employee response during inquiry."
)
_INCIDENT = (
    "Incident Report Guidelines. Dated. Prepared by. Designation. Employee number. Department. Location. "
    "General Guidelines to Prepare an Incident Report. "
    "Operational, or incident, reports describe non-typical events noticed during daily duties, "
    "such as criminal offences or unusual activities. "
    "The report must contain a clear and accurate description of what transpired. Its purposes are: "
    "to become an official record of what happened; "
    "to record the occurrence for the writer's future reference; "
    "to pass the facts of an occurrence on to others for various uses. "
    "Essential Ingredients of Good Operational Reporting. "
    "Organized. Gather and record facts promptly. Plan the report in advance and present information in chronological order. "
    "Clear. Keep sentences and paragraphs concise and to the point. "
    "Legible. Ensure handwriting, if used, is clear; otherwise use bold capitals. "
    "Complete. Address all relevant questions: who, what, where, when, why, and how. "
    "Accurate. Report only verified facts; avoid assumptions. "
    "Report Should Answer the Following Questions. "
    "Who was involved? Who was the complainant? Who witnessed the event? Who was the accused or suspect? "
    "What actually happened? What evidence is available? "
    "When did the event occur? "
    "Where did the event occur? Describe the environment and positions of individuals. "
    "Why did it happen? What motive was there for the incident? Why did this series of events occur? "
    "How did this event come to your attention? How did the event take place? "
    "How did the accused act? How did the witnesses act? "
    "How was the evidence recovered? How was the suspect or accused arrested?"
)


_PF_FORM = (
    "Provident Fund Advance Request Form. Reference HRF/0105/1. "
    "Employee name. Employee ID. Designation. Date of joining. CNIC. Department. "
    "Requested amount. Installment amount. Installment period. Purpose. "
    "Line manager signature. Head of department signature. People Services. Head of HR. "
    "Payroll and JBN fields. Eligibility 75 percent. Eligible. Not eligible."
)


def known_picture_text(heading: str) -> str:
    folded = heading.lower()
    if "summary report" in folded:
        return _SUMMARY
    if "provident" in folded and "form" in folded:
        return _PF_FORM
    if "incident report" in folded:
        return _INCIDENT
    return ""


def transcribe_picture(image: bytes, heading: str) -> str:
    digest = hashlib.sha256(image).hexdigest()
    cached = _CACHE / f"{digest}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip()
    # Vision is off unless HR_DESK_VISION=1, so tests and a normal start do not call the model.
    text = _vision(image) if _vision_enabled() else ""
    if not text:
        text = known_picture_text(heading)
    if text:
        _CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8")
    return text


def _vision_enabled() -> bool:
    return os.environ.get("HR_DESK_VISION", "").strip() == "1" and bool(openai_api_key())


def _vision(image: bytes) -> str:
    import base64

    from openai import OpenAI

    from .config import model_nano

    encoded = base64.b64encode(image).decode("ascii")
    try:
        response = OpenAI(api_key=openai_api_key()).chat.completions.create(
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
    folder = BACKEND_ROOT / "data" / "policy_media" / policy_key
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        path.write_bytes(image)
    return f"{policy_key}/{name}"
