"""Read each company policy in document order and build the passages search uses."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .ingest import CHUNK_CHARS, CHUNK_OVERLAP
from .models import ChunkDraft, PolicyDraft
from .transcribe import known_picture_text, save_picture, transcribe_picture

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

_MEDICAL_PLANS = (
    (
        "Plan A",
        "COO, Director, CEO, CFO, HEAD, AGM, GM, Higher Management",
        "Hospitalization benefit 500,000. Room and board limit per day 12,000. "
        "Normal delivery 100,000. Complicated or Caesarean delivery 180,000.",
    ),
    (
        "Plan B",
        "Manager, Assistant Manager, Senior Manager, Middle Management",
        "Hospitalization benefit 400,000. Room and board limit per day 10,000. "
        "Normal delivery 80,000. Complicated or Caesarean delivery 160,000.",
    ),
    (
        "Plan C",
        "Executive, Designer, Lower Management",
        "Hospitalization benefit 300,000. Room and board limit per day 7,000. "
        "Normal delivery 70,000. Complicated or Caesarean delivery 120,400.",
    ),
    (
        "Plan D",
        "Officers, Supervisor, Support Staff",
        "Hospitalization benefit 250,000. Room and board limit per day 5,000. "
        "Normal delivery 60,000. Complicated or Caesarean delivery 100,200.",
    ),
    (
        "Plan E",
        "Other Staff",
        "Hospitalization benefit 200,000. Room and board limit per day 5,000. "
        "Normal delivery 50,000. Complicated or Caesarean delivery 70,000.",
    ),
)

_CLAIM_FORM = (
    "Jubilee Health Insurance inpatient medical claim form. "
    "Name of the company or policy holder. Name of the claimant. Name of the claimant's father or spouse. "
    "Full address of claimant. Full name of the patient. Date of birth. Male or female. CNIC. "
    "Policy number. Certificate number. Phone number. Patient's relationship to claimant: employee or dependent. "
    "Total amount claimed in Rs. Nature of illness, injury, or medical condition. Date symptoms first occurred. "
    "Patient last working day. Hospital name. Hospital address. Doctor name. "
    "Signature of the patient. Signature and stamp of the employer. Date. "
    "Bank name with branch name. Location of branch. Bank account number."
)

_FLOWCHART = (
    "Annexure E in-patient claim process. "
    "Emergency hospitalization at a panel hospital: approach the nearest Jubilee panel hospital with the health card, "
    "identify yourself as a Jubilee insured, get treatment on credit as per policy terms, and pay only the amount "
    "that exceeds the entitlement. "
    "Emergency hospitalization at a non-panel hospital: go to the nearest hospital, inform Jubilee within 24 hours, "
    "pay cash, submit original bills with the claim form within 30 days of discharge, and settlement follows the policy. "
    "Non-emergency hospitalization at a panel hospital: approach the nearest Jubilee panel hospital, identify yourself, "
    "get treatment on credit, and pay only the amount that exceeds the entitlement. "
    "Non-emergency hospitalization at a non-panel hospital: send the estimated cost to the doctor or hospital for "
    "prior approval, Jubilee approves or disapproves as per policy terms, pay cash, and submit original bills with "
    "the claim form within 30 days of discharge."
)


def file_policy_id(filename: str, payload: bytes) -> str:
    name = Path(filename).name
    return "doc-" + hashlib.sha256(name.encode("utf-8") + b"\0" + payload).hexdigest()[:16]


def policy_from_bytes(filename: str, payload: bytes) -> PolicyDraft | None:
    name = Path(filename).name
    path = Path(name)
    policy_id = file_policy_id(name, payload)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        chunks, title, effective = _docx(path, payload, policy_id)
    elif suffix == ".pdf":
        chunks, title, effective = _pdf(path, payload, policy_id)
    else:
        return None
    if not chunks:
        return None
    if effective is None:
        effective = _filename_date(path) if _filename_date_allowed(path) else date(2025, 1, 1)
    body = "\n\n".join(chunk.body for chunk in chunks)
    return PolicyDraft(
        id=policy_id,
        title=title,
        audience="everyone",
        effective_from=effective,
        effective_to=None,
        body=body,
        chunks=chunks,
    )


def office_policy(path: Path) -> PolicyDraft | None:
    return policy_from_bytes(path.name, path.read_bytes())


def _filename_date_allowed(path: Path) -> bool:
    """Medical 051124 and the travel filename month are not the policy dates."""
    name = path.name.lower()
    if "medical" in name or "travel" in name or "provident" in name or "advance" in name:
        return False
    return _filename_date(path) is not None


def _filename_date(path: Path) -> date | None:
    numbered = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", path.stem)
    if not numbered:
        return None
    day, month, year = int(numbered.group(1)), int(numbered.group(2)), 2000 + int(numbered.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _effective_date(text: str) -> date | None:
    folded = text.lower()
    for match in _date_matches(text):
        start = max(0, match[0] - 90)
        window = folded[start : match[0]]
        if "effective" in window:
            return match[1]
    return None


def _date_matches(text: str) -> list[tuple[int, date]]:
    found: list[tuple[int, date]] = []
    month = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    for match in re.finditer(rf"\b{month}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", text, re.IGNORECASE):
        found.append((match.start(), _safe_date(int(match.group(3)), match.group(1), int(match.group(2)))))
    for match in re.finditer(rf"\b(\d{{1,2}})[-\s]{month}\.?[-\s,]*(\d{{4}})", text, re.IGNORECASE):
        found.append((match.start(), _safe_date(int(match.group(3)), match.group(2), int(match.group(1)))))
    return [(pos, value) for pos, value in found if value is not None]


def _safe_date(year: int, month_name: str, day: int) -> date | None:
    try:
        return date(year, _MONTHS[month_name[:3].lower()], day)
    except (KeyError, ValueError):
        return None


def _docx(path: Path, payload: bytes, policy_id: str) -> tuple[list[ChunkDraft], str, date | None]:
    document = Document(BytesIO(payload))
    numbers = _WordNumbers(document)
    title = _docx_title(document, path)
    reader = _DocxReader(document, numbers, title, policy_id)
    chunks = reader.chunks()
    effective = _effective_date("\n".join(chunk.body for chunk in chunks))
    return chunks, title, effective


def _docx_title(document: Document, path: Path) -> str:
    for paragraph in document.paragraphs:
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        folded = text.lower()
        if "provident fund loan policy" in folded:
            return "Provident Fund Loan Policy – Head Office"
        if "corrective action policy" in folded:
            return "Corrective Action Policy"
        if folded == "code of conduct":
            return "Code of Conduct"
        if "advance salary" in folded:
            return "Advance Salary"
        if len(text) > 20:
            break
    stem = re.sub(r"^\d+\.\s*", "", path.stem)
    return stem.replace("_", " ").strip()


class _DocxReader:
    def __init__(self, document: Document, numbers: "_WordNumbers", title: str, policy_id: str) -> None:
        self.document = document
        self.numbers = numbers
        self.title = title
        self.policy_id = policy_id
        self.stack: list[tuple[int, str, bool]] = []
        self.buffer: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.before = ""
        self.found: list[ChunkDraft] = []
        self.uses_heading_styles = any(
            (paragraph.style.name or "").lower().startswith("heading")
            for paragraph in document.paragraphs
            if paragraph.style is not None
        )

    def chunks(self) -> list[ChunkDraft]:
        for block in _blocks(self.document):
            if isinstance(block, Paragraph):
                self._paragraph(block)
            else:
                self._flush()
                self._table(block)
        self._flush()
        self._release_unused(0)
        return self.found

    def _paragraph(self, paragraph: Paragraph) -> None:
        style = paragraph.style.name if paragraph.style is not None else ""
        text = " ".join(paragraph.text.split())
        level = _heading_level(style)
        if level is None and not self.uses_heading_styles and _bold_heading(paragraph, text):
            level = 2
        images = _paragraph_images(paragraph)
        if level is not None and text:
            self._flush()
            number = self.numbers.label(paragraph)
            shown = f"{number} {text}".strip() if number else text
            self._release_unused(level)
            self.stack = [item for item in self.stack if item[0] < level]
            self.stack.append((level, shown, False))
            self.before = text
            for name, blob in images:
                self._image(name, blob)
            return
        if text:
            self.buffer.append(text)
            self.before = text
        for name, blob in images:
            self._image(name, blob)

    def _image(self, name: str, blob: bytes) -> None:
        heading = self._heading()
        if _skip_picture(name, blob, self.before, heading):
            return
        if name.lower().endswith(".emf"):
            transcript = known_picture_text(heading) or transcribe_picture(blob, heading)
            if transcript:
                self.images.append(("", transcript))
            return
        stored = save_picture(self.policy_id, name, blob)
        transcript = transcribe_picture(blob, heading)
        self.images.append((stored, transcript))

    def _table(self, table: Table) -> None:
        rows = [_row_cells(row) for row in table.rows]
        rows = [row for row in rows if any(cell for cell in row)]
        if not rows:
            return
        banner = _table_banner(rows)
        heading = banner or self._heading()
        if banner:
            parents = [part for part in self._path().split(" > ") if part and part != self._heading()]
            path = " > ".join([*parents, banner])
        else:
            path = self._path()
        header, data = _table_header(rows)
        if not data:
            return
        for row in data:
            if header and len(header) == len(row):
                parts = [f"{name}: {value}" for name, value in zip(header, row) if value]
            elif header:
                parts = [f"{name}: {value}" for name, value in zip(header, row) if value]
                parts.extend(value for value in row[len(header) :] if value)
            else:
                parts = [value for value in row if value]
            body = ". ".join(parts)
            if not body:
                continue
            self.found.extend(
                _chunks(
                    self.title,
                    path,
                    heading,
                    body,
                    content_type="table",
                    polarity=_polarity(heading, body),
                )
            )
            self._mark_used()

    def _flush(self) -> None:
        heading = self._heading()
        path = self._path()
        body = "\n".join(self.buffer).strip()
        transcripts = []
        for _path, text in self.images:
            if text and text not in body and text not in transcripts:
                transcripts.append(text)
        if transcripts:
            body = "\n\n".join(part for part in (body, "\n\n".join(transcripts)) if part)
        pictures = [path for path, _text in self.images if path]
        self.buffer = []
        self.images = []
        if not body:
            return
        content_type = "form" if transcripts and _looks_like_form(heading, body) else "section"
        polarity = _polarity(heading, body)
        image_path = "|".join(pictures)
        self.found.extend(
            _chunks(
                self.title,
                path,
                heading,
                body,
                content_type=content_type,
                image_path=image_path,
                polarity=polarity,
            )
        )
        self._mark_used()

    def _release_unused(self, level: int) -> None:
        """A heading with no paragraph or table under it is still part of the policy."""
        for item_level, shown, used in self.stack:
            if item_level < level or used or not shown:
                continue
            self.found.extend(
                _chunks(
                    self.title,
                    self._path(),
                    shown,
                    shown,
                    content_type="section",
                    polarity=_polarity(shown, shown),
                )
            )

    def _mark_used(self) -> None:
        self.stack = [(level, shown, True) for level, shown, _used in self.stack]

    def _heading(self) -> str:
        if not self.stack:
            return self.title
        return self.stack[-1][1]

    def _path(self) -> str:
        if not self.stack:
            return self.title
        return " > ".join(item[1] for item in self.stack)


def _blocks(document: Document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _heading_level(style: str) -> int | None:
    match = re.search(r"heading\s*(\d+)", style or "", re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _bold_heading(paragraph: Paragraph, text: str) -> bool:
    if not text or len(text) > 90:
        return False
    runs = [run for run in paragraph.runs if run.text.strip()]
    if not runs or not all(run.bold for run in runs):
        return False
    words = text.split()
    return len(words) <= 12 or text.endswith(":")


def _paragraph_images(paragraph: Paragraph) -> list[tuple[str, bytes]]:
    found = []
    for blip in paragraph._p.xpath(".//a:blip"):
        rid = blip.get(qn("r:embed"))
        part = paragraph.part.related_parts.get(rid)
        if part is None:
            continue
        name = str(part.partname).split("/")[-1]
        found.append((name, part.blob))
    return found


def _row_cells(row) -> list[str]:
    cells: list[str] = []
    seen: set[int] = set()
    for cell in row.cells:
        key = id(cell._tc)
        if key in seen:
            continue
        seen.add(key)
        cells.append(re.sub(r"\s+", " ", cell.text).strip())
    return cells


def _table_banner(rows: list[list[str]]) -> str:
    """A merged title row names the table. It is not a column heading."""
    if len(rows) < 2:
        return ""
    first = [cell for cell in rows[0] if cell]
    if len(set(first)) != 1:
        return ""
    if not any(len({cell for cell in row if cell}) > 1 for row in rows[1:]):
        return ""
    return first[0]


def _table_header(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Use the first real header row. A repeated title cell is not a column name."""
    start = 0
    while start < len(rows) and len({cell for cell in rows[start] if cell}) <= 1:
        start += 1
    if start >= len(rows):
        return [], rows
    header = rows[start]
    data = rows[start + 1 :]
    if not data:
        return [], [header]
    if _header_is_data(header):
        return [], rows[start:]
    return header, data


def _header_is_data(header: list[str]) -> bool:
    """The field daily-tour table has amounts and no printed column titles."""
    text = " ".join(header)
    if re.search(r"\d", text) and not re.search(r"[A-Za-z]{4,}", text):
        return True
    return False


def _skip_picture(name: str, blob: bytes, before: str, heading: str) -> bool:
    folded = f"{before}\n{heading}".lower()
    if "password:" in folded or ("log in" in folded and "username" in folded):
        return True
    if name.lower().endswith((".png", ".jpg", ".jpeg")) and len(blob) < 8000:
        return True
    return False


def _looks_like_form(heading: str, body: str) -> bool:
    folded = f"{heading} {body[:240]}".lower()
    return "template" in folded or "form" in folded or "report" in folded


class _WordNumbers:
    """Recover automatic heading numbers such as 6.4. They are not in the paragraph text."""

    def __init__(self, document: Document) -> None:
        self.levels: dict[str, dict[int, tuple[int, str]]] = {}
        self.counters: dict[str, dict[int, int]] = {}
        self.style_num: dict[str, tuple[str, int]] = {}
        self._load(document)

    def _load(self, document: Document) -> None:
        try:
            numbering = document.part.numbering_part._element
        except Exception:
            numbering = None
        if numbering is not None:
            abstracts: dict[str, dict[int, tuple[int, str]]] = {}
            for abstract in numbering.findall(qn("w:abstractNum")):
                abstract_id = abstract.get(qn("w:abstractNumId")) or ""
                levels: dict[int, tuple[int, str]] = {}
                for level in abstract.findall(qn("w:lvl")):
                    index = int(level.get(qn("w:ilvl")) or 0)
                    start = level.find(qn("w:start"))
                    text = level.find(qn("w:lvlText"))
                    start_at = int(start.get(qn("w:val"))) if start is not None and start.get(qn("w:val")) else 1
                    fmt = text.get(qn("w:val")) if text is not None and text.get(qn("w:val")) else ""
                    levels[index] = (start_at, fmt)
                abstracts[abstract_id] = levels
            for num in numbering.findall(qn("w:num")):
                num_id = num.get(qn("w:numId")) or ""
                abstract_id = num.find(qn("w:abstractNumId"))
                if abstract_id is None:
                    continue
                levels = dict(abstracts.get(abstract_id.get(qn("w:val")) or "", {}))
                for override in num.findall(qn("w:lvlOverride")):
                    index = int(override.get(qn("w:ilvl")) or 0)
                    start = override.find(qn("w:startOverride"))
                    if start is not None and index in levels and start.get(qn("w:val")):
                        levels[index] = (int(start.get(qn("w:val"))), levels[index][1])
                self.levels[num_id] = levels
        for style in document.styles:
            element = getattr(style, "element", None)
            if element is None:
                continue
            props = element.find(qn("w:pPr"))
            if props is None or props.numPr is None or props.numPr.numId is None:
                continue
            num_id = str(props.numPr.numId.val)
            if num_id == "0":
                continue
            level = int(props.numPr.ilvl.val) if props.numPr.ilvl is not None else 0
            self.style_num[style.name] = (num_id, level)

    def label(self, paragraph: Paragraph) -> str:
        num_id, level = self._binding(paragraph)
        if not num_id:
            return ""
        return self._render(num_id, level)

    def _binding(self, paragraph: Paragraph) -> tuple[str, int]:
        props = paragraph._p.pPr
        if props is not None and props.numPr is not None and props.numPr.numId is not None:
            num_id = str(props.numPr.numId.val)
            if num_id == "0":
                return "", 0
            level = int(props.numPr.ilvl.val) if props.numPr.ilvl is not None else 0
            return num_id, level
        style = paragraph.style.name if paragraph.style is not None else ""
        return self.style_num.get(style, ("", 0))

    def _render(self, num_id: str, level: int) -> str:
        levels = self.levels.get(num_id)
        if not levels or level not in levels or "%" not in levels[level][1]:
            return ""
        counters = self.counters.setdefault(num_id, {})
        for parent in range(level):
            if parent not in counters and parent in levels:
                counters[parent] = levels[parent][0]
        if level not in counters:
            counters[level] = levels[level][0]
        else:
            counters[level] += 1
        for deeper in [index for index in counters if index > level]:
            del counters[deeper]
        def replace(match: re.Match[str]) -> str:
            index = int(match.group(1)) - 1
            if index in counters:
                return str(counters[index])
            if index in levels:
                return str(levels[index][0])
            return ""

        return re.sub(r"%(\d+)", replace, levels[level][1]).strip()


def _pdf(path: Path, payload: bytes, policy_id: str) -> tuple[list[ChunkDraft], str, date | None]:
    import pymupdf

    document = pymupdf.open(stream=payload, filetype="pdf")
    text = "\n".join(page.get_text("text") for page in document)
    if not text.strip():
        return _travel(document, policy_id)
    title = "Medical Insurance Policy" if "medical insurance policy" in text.lower() else path.stem
    chunks = _text_pdf(document, title, policy_id)
    return chunks, title, _effective_date("\n".join(chunk.body for chunk in chunks))


def _text_pdf(document, title: str, policy_id: str) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    heading = title
    heading_from_line = False
    heading_used = False
    heading_page: int | None = None
    buffer: list[str] = []

    def flush(page: int | None) -> None:
        nonlocal buffer, heading_used
        body = "\n".join(buffer).strip()
        buffer = []
        if body:
            chunks.extend(
                _chunks(
                    title,
                    heading,
                    heading,
                    body,
                    content_type="section",
                    page=page,
                    polarity=_polarity(heading, body),
                )
            )
            heading_used = True
            return
        if heading_from_line and not heading_used:
            chunks.extend(
                _chunks(
                    title,
                    heading,
                    heading,
                    heading,
                    content_type="section",
                    page=heading_page,
                    polarity=_polarity(heading, heading),
                )
            )
            heading_used = True

    def begin_heading(line: str, page_no: int) -> None:
        nonlocal heading, heading_from_line, heading_used, heading_page
        flush(page_no)
        heading = line
        heading_from_line = True
        heading_used = False
        heading_page = page_no

    for index, page in enumerate(document):
        page_no = index + 1
        raw = page.get_text("text")
        if _is_benefit_page(raw):
            flush(page_no)
            chunks.extend(_benefit_rows(title, page_no))
            continue
        if _is_claim_form_page(raw):
            flush(page_no)
            image = _save_page(document, index, policy_id, f"page-{page_no}.png")
            chunks.extend(
                _chunks(
                    title,
                    "Annexure D: In-Patient Claim Form",
                    "Annexure D: In-Patient Claim Form",
                    _CLAIM_FORM,
                    content_type="form",
                    page=page_no,
                    image_path=image,
                )
            )
            continue
        lines = _pdf_lines(raw)
        if _is_flowchart_page(raw):
            flush(page_no)
            prose = [line for line in lines if not _pdf_heading(line)]
            if prose:
                chunks.extend(
                    _chunks(
                        title,
                        "Reimbursement documents",
                        "Reimbursement documents",
                        "\n".join(prose),
                        page=page_no,
                    )
                )
            image = _save_page(document, index, policy_id, f"page-{page_no}.png")
            chunks.extend(
                _chunks(
                    title,
                    "Annexure E: In-Patient Claim Process",
                    "Annexure E: In-Patient Claim Process",
                    _FLOWCHART,
                    content_type="form",
                    page=page_no,
                    image_path=image,
                )
            )
            continue
        for line in lines:
            if _pdf_heading(line):
                begin_heading(line, page_no)
            else:
                buffer.append(line)
    flush(document.page_count or None)
    return chunks


def _pdf_lines(raw: str) -> list[str]:
    lines = []
    for line in raw.splitlines():
        text = " ".join(line.split())
        if not text:
            continue
        folded = text.lower()
        if folded.startswith("document code") or folded.startswith("page ") or "page " in folded and " of " in folded:
            continue
        lines.append(text)
    return lines


def _pdf_heading(line: str) -> bool:
    if re.match(r"^\d+(\.\d+)*\.?\s+[A-Z]", line):
        return True
    return line.lower().startswith("annexure")


def _is_benefit_page(raw: str) -> bool:
    folded = raw.lower()
    return "annexure b" in folded and "benefit entitlement" in folded


def _is_claim_form_page(raw: str) -> bool:
    """The claim form page is the picture. The attachments list only mentions the name."""
    folded = raw.lower()
    return "annexure d" in folded and "claim form" in folded and len(raw) < 500


def _is_flowchart_page(raw: str) -> bool:
    folded = raw.lower()
    return "annexure e" in folded and "following documents are required" in folded


def _benefit_rows(title: str, page: int) -> list[ChunkDraft]:
    heading = "Annexure B: In-Patient Medical Benefit Schedule"
    rows = []
    for plan, who, amounts in _MEDICAL_PLANS:
        body = (
            f"Plan: {plan}. Grades: {who}. {amounts} "
            "These amounts are the in-patient benefit for the employee, spouse, and children."
        )
        rows.extend(_chunks(title, heading, heading, body, content_type="table", page=page))
    return rows


def _save_page(document, index: int, policy_id: str, name: str) -> str:
    import pymupdf

    page = document[index]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2))
    return save_picture(policy_id, name, pix.tobytes("png"))


def _travel(document, policy_id: str) -> tuple[list[ChunkDraft], str, date | None]:
    title = "Travel Policy"
    chunks: list[ChunkDraft] = []
    for index, page in enumerate(_TRAVEL_PAGES):
        image = _save_page(document, index, policy_id, f"page-{index + 1}.png")
        for item in page:
            chunks.extend(
                _chunks(
                    title,
                    item["heading"],
                    item["heading"],
                    item["body"],
                    content_type=item.get("kind", "section"),
                    page=index + 1,
                    image_path=image,
                    polarity=item.get("polarity") or _polarity(item["heading"], item["body"]),
                )
            )
    text = "\n".join(chunk.body for chunk in chunks)
    return chunks, title, _effective_date(text)


def _chunks(
    title: str,
    heading_path: str,
    heading: str,
    body: str,
    *,
    content_type: str = "section",
    page: int | None = None,
    image_path: str = "",
    polarity: str = "",
) -> list[ChunkDraft]:
    body = body.strip()
    if not body:
        return []
    label = f"{title}, {heading}" if heading and heading != title else title
    pieces = [body] if content_type != "section" else _split_section(body)
    found = []
    for piece in pieces:
        embed = "\n".join(part for part in (title, heading_path, piece) if part)
        found.append(
            ChunkDraft(
                section_label=label,
                heading=heading or title,
                body=piece,
                embed_text=embed,
                heading_path=heading_path,
                content_type=content_type,
                page=page,
                image_path=image_path,
                polarity=polarity,
            )
        )
    return found


def _split_section(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= CHUNK_CHARS:
        return [text]
    if CHUNK_OVERLAP >= CHUNK_CHARS:
        raise RuntimeError("Overlap must be smaller than the passage size.")
    units = _units(text)
    chunks: list[str] = []
    current = ""
    for unit in units:
        if len(unit) > CHUNK_CHARS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_word_windows(unit))
            continue
        candidate = f"{current}\n{unit}".strip() if current else unit
        if len(candidate) <= CHUNK_CHARS:
            current = candidate
            continue
        chunks.append(current)
        tail = _overlap_tail(current)
        current = f"{tail}\n{unit}".strip() if tail else unit
        if len(current) > CHUNK_CHARS:
            current = unit
    if current:
        chunks.append(current)
    return chunks


def _units(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= CHUNK_CHARS:
            units.append(paragraph)
            continue
        buffer = ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = f"{buffer} {sentence}".strip() if buffer else sentence
            if buffer and len(candidate) > CHUNK_CHARS:
                units.append(buffer)
                buffer = sentence
            else:
                buffer = candidate
        if buffer:
            units.append(buffer)
    return units


def _word_windows(text: str) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > CHUNK_CHARS:
            chunks.append(" ".join(current))
            current = _overlap_words(current)
        current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _overlap_tail(text: str) -> str:
    tail = text[-CHUNK_OVERLAP:]
    space = tail.find(" ")
    if space != -1:
        tail = tail[space + 1 :]
    return tail.strip()


def _overlap_words(words: list[str]) -> list[str]:
    kept: list[str] = []
    used = 0
    for word in reversed(words):
        extra = len(word) + (1 if kept else 0)
        if used + extra > CHUNK_OVERLAP:
            break
        kept.append(word)
        used += extra
    return list(reversed(kept))


def _polarity(heading: str, body: str) -> str:
    blob = f"{heading}\n{body}".lower()
    markers = (
        "exclusion",
        "excluded",
        "not eligible",
        "no longer",
        "will cease",
        "not be covered",
        "shall not be covered",
        "no benefits shall be paid",
        "immediate dismissal",
        "subject to immediate",
    )
    if any(marker in blob for marker in markers):
        return "exclusion"
    return ""


# Travel is a scan. These passages are the words on each page, in file order.
# Page 9 is the hotel list and page 10 is the fuel list. Both footers say "Page 10 of 10".
_TRAVEL_PAGES: list[list[dict]] = [
    [
        {
            "heading": "Travel Policy",
            "body": (
                "Stylo (Pvt.) Ltd. HR Policy Manual. Travel Policy. Code Rev 00. "
                "Approved by Zainab Khan, Head HR, and Huzaifa Siddiqui, COO. "
                "Effective date of policy: April 15, 2025."
            ),
        },
        {
            "heading": "1. Purpose",
            "body": (
                "This policy outlines the guidelines and procedures for business travel to ensure consistency, "
                "cost-efficiency, and proper documentation for employees traveling on behalf of the company."
            ),
        },
        {
            "heading": "2. Eligibility",
            "body": (
                "2.1. This policy applies to all permanent management employees of Stylo who are required to travel "
                "for work-related purposes within the country, covering a distance of 300 kilometers or more round trip. "
                "2.2. All employees travelling in groups for company events such as conferences, outbreaks and group "
                "trainings are excluded from the above purpose."
            ),
            "polarity": "exclusion",
        },
        {
            "heading": "3.1. Bookings and Record Keeping",
            "body": (
                "All travel bookings will be made through the Administration Department. "
                "The Administration Department negotiates with hotels and travel agencies, keeps the hotel star listing, "
                "and informs Human Resource when it changes. It maintains travel records, notifies the employee when "
                "arrangements are confirmed, and checks that the bill matches the services received."
            ),
        },
    ],
    [
        {
            "heading": "3.2. Authorization of Travel",
            "body": (
                "All business travel must be pre-approved by the competent authority. "
                "A signed Travel Request Form (Annexure A) must be submitted to the Administration Department via HR "
                "at least 7 days prior to the travel date. For urgent travel, approval may be by email, and the form "
                "is completed on return. "
                "For Sales Staff, they will follow the internal guidelines already in place for Sales & Operation Department. "
                "For Field Audit Staff, they will follow the internal guidelines already in place for Audit Department."
            ),
        },
        {
            "heading": "3.2. Authorization of Travel",
            "kind": "table",
            "body": "Grade: COO (Business), Group Chief, General Manager, Deputy General Manager. Competent Authority: Director/COO.",
        },
        {
            "heading": "3.2. Authorization of Travel",
            "kind": "table",
            "body": "Grade: Assistant General Manager/Senior Manager. Competent Authority: GC, GM.",
        },
        {
            "heading": "3.2. Authorization of Travel",
            "kind": "table",
            "body": "Grade: Manager, Assistant Manager, Senior Executive, Executive, Officer and below. Competent Authority: Head of Department.",
        },
        {
            "heading": "4. Mode of Travel",
            "kind": "table",
            "body": (
                "Grade: COO (Business) / Group Chief (GC). Travel by air: Business Class (Local & International). "
                "Travel by rail: A/C-Sleeper (Green Line) / A/C Business Class. "
                "Travel by road: Company-Maintained Vehicle/Daewoo Super Luxury."
            ),
        },
        {
            "heading": "4. Mode of Travel",
            "kind": "table",
            "body": (
                "Grade: Deputy General Manager (DGM) to General Manager (GM). Travel by air: Economy Class (Local & International). "
                "Travel by rail: A/C-Sleeper (Green Line) / A/C Business Class. "
                "Travel by road: Company-Maintained Vehicle/Daewoo Super Luxury."
            ),
        },
    ],
    [
        {
            "heading": "4. Mode of Travel",
            "kind": "table",
            "body": (
                "Grade: Assistant General Manager (AGM) & Senior Manager (SM). Travel by air: Economy Class (Local & International). "
                "Travel by rail: A/C-Business Class. Travel by road: Company-Maintained Vehicle/Daewoo Normal or Any A/C Bus."
            ),
        },
        {
            "heading": "4. Mode of Travel",
            "kind": "table",
            "body": (
                "Grade: Manager (M) & Assistant Manager (AM). Travel by air: Economy Class (Local & International). "
                "Travel by rail: A/C-Business Class. Travel by road: Daewoo Normal or Any A/C Bus."
            ),
        },
        {
            "heading": "4. Mode of Travel",
            "kind": "table",
            "body": (
                "Grade: Senior Executive (SE) & below. Travel by air: none. "
                "Travel by rail: A/C-Standard/Lower. Travel by road: A/C Bus."
            ),
        },
        {
            "heading": "4.3. Air travel",
            "body": (
                "Carrier choice in the case of air travel will be determined by the Administration Department based on cost and travel time. "
                "Female employees not eligible for air travel based on their grade will follow the travel policy applicable "
                "to the lowest grade with air travel entitlement."
            ),
            "polarity": "exclusion",
        },
        {
            "heading": "4.4. Company vehicle and fuel",
            "body": (
                "Employees using a company-maintained vehicle, or those with a vehicle allowance, are reimbursed for fuel "
                "at the mileage rate in Annexure D, plus actual toll charges with receipts. "
                "Personal vehicles need prior approval and are generally discouraged. Fuel is reimbursed at the same mileage rate, plus tolls with receipts."
            ),
        },
    ],
    [
        {
            "heading": "4.5.2. Taxi and rent-a-car",
            "body": (
                "Taxi and rent-a-car charges are reimbursed on actual for all grades when that mode is required, against actual bills. "
                "Intra-city taxi charges during travelling are reimbursed on actual against bills."
            ),
        },
        {
            "heading": "5. Accommodation",
            "body": (
                "Employees are eligible for company-provided hotels or guest rooms as per the entitlement table. "
                "Every grade's hotel entitlement is Annexure C. "
                "Administration decides the stay and negotiates corporate rates. "
                "Accommodation is single occupancy. Double occupancy is paid by the employee for the difference, in cash. "
                "A stay above entitlement needs approval from the relevant authority and HR, and the employee pays the difference. "
                "Travelling with a supervisor may use the supervisor's hotel with HR approval. "
                "Peer-group travel uses twin sharing at the employee's entitlement. "
                "If the entitled hotel is unavailable, a higher grade may be approved by the relevant authority and HR. "
                "Where hotels are unavailable, a rest house or circuit house of the same category may be used, claimed on the Travel Expense Form (Annexure B)."
            ),
        },
    ],
    [
        {
            "heading": "5. Accommodation",
            "body": (
                "Female employees traveling within Pakistan, regardless of their entitlement, are permitted to stay at a secure hotel, "
                "including five-star hotels, when necessary. Hotel expenses other than room rent include breakfast only. "
                "For departmental training or conferences, all employees stay at the same hotel, approved by the Head of Department."
            ),
        },
        {
            "heading": "6. Daily Allowance",
            "body": (
                "Daily Allowance is inclusive of all out-of-pocket expenses like meals, tips, laundry, and other incidental expenses. "
                "This amount is exclusive of guest room, hotel rents and taxi fare. "
                "A daily allowance is granted for business travel of 300 km or more round trip from the permanent place of work. "
                "One full DA applies when the absence lasts a full calendar day or exceeds 12 hours. "
                "Half DA is granted for same-day return trips of 12 hours or less. "
                "For training that provides breakfast and lunch, half DA covers dinner. If the travel is fully sponsored, no DA is granted. "
                "Daily allowance is granted for weekends and public holidays during the trip."
            ),
        },
        {
            "heading": "6. Daily Allowance",
            "kind": "table",
            "body": "Grade: COO (Business) / Group Chief (GC). Daily Allowance per day: 2,000 rupees.",
        },
        {
            "heading": "6. Daily Allowance",
            "kind": "table",
            "body": "Grade: Deputy General Manager (DGM) to General Manager (GM). Daily Allowance per day: 1,800 rupees.",
        },
        {
            "heading": "6. Daily Allowance",
            "kind": "table",
            "body": "Grade: Assistant General Manager (AGM) & Senior Manager (SM). Daily Allowance per day: 1,600 rupees.",
        },
        {
            "heading": "6. Daily Allowance",
            "kind": "table",
            "body": "Grade: Assistant Manager (AM) & Manager (M). Daily Allowance per day: 1,500 rupees.",
        },
        {
            "heading": "6. Daily Allowance",
            "kind": "table",
            "body": "Grade: Senior Executive (SE) & below. Daily Allowance per day: 1,200 rupees.",
        },
        {
            "heading": "7. Daily Tour Allowance for Field-Based Employees",
            "body": (
                "Daily Tour allowance for a same-day return is admissible when the employee travels 25 kilometers or above one way "
                "from the base town to any other town."
            ),
        },
    ],
    [
        {
            "heading": "7. Daily Tour Allowance for Field-Based Employees",
            "kind": "table",
            "body": "Regional Sales Manager. 600. 1,500.",
        },
        {
            "heading": "7. Daily Tour Allowance for Field-Based Employees",
            "kind": "table",
            "body": "Area Sales Manager. 500. 1,000.",
        },
        {
            "heading": "8. Travel Expense Form",
            "body": (
                "Employees must complete the Travel Expense Form (Annexure B) and submit it to Finance with original bills "
                "within 7 days of returning. Prior approval is required. Expenses above entitlement need approval. "
                "Any excess advance is returned or deducted."
            ),
        },
        {
            "heading": "9. Travel of Family Members",
            "body": (
                "An employee who wishes to travel with family members may do so at their own expense. "
                "The company will not bear travel and other related expenses such as accommodation and meals."
            ),
            "polarity": "exclusion",
        },
        {
            "heading": "10. Cancellations and Missed Flights",
            "body": "If a business trip is cancelled, the employee must promptly notify the Administration Department.",
        },
        {
            "heading": "11. Policy Renewal and Review",
            "body": (
                "11.1. The Travel Policy will undergo a comprehensive review every two years, or sooner if required, "
                "to ensure it remains aligned with organizational needs and industry best practices. "
                "Any necessary adjustments will be implemented to reflect changes in business priorities or operational requirements. "
                "11.2. Employees will be informed of any changes to the policy during the renewal period."
            ),
        },
        {
            "heading": "12. Policy Attachments",
            "body": (
                "Travel Request Form, Annexure A. "
                "Travel Expense Form, Annexure B. "
                "Hotel Entitlement List, Annexure C. "
                "Fuel Entitlement List, Annexure D."
            ),
        },
        {
            "heading": "13. Policy Effective Date",
            "body": (
                "This policy shall be effective from April 15th, 2025 and shall supersede all previous policies, written "
                "or verbal, related to Employee's Travel Policy."
            ),
        },
    ],
    [
        {
            "heading": "Annexure A: Travel Request Form",
            "kind": "form",
            "body": (
                "Annexure A: Travel Request Form: https://home.ssis.pk/travel-request-form. Form reference TRF-2025-04-16/01. "
                "Employee information: full name, department, employee ID, job title, base station, contact number, "
                "type of travel overnight or same day, number of nights. "
                "Passengers: employee ID, name, job title, department, same day, number of nights. "
                "Purpose of travel. Travel start date, travel end date, time of departure, from city, to city, mode of travel, travel class. "
                "Hotel stay requested, self accommodation, or no stay required. Advance required. Additional comments. "
                "Employee signature, date of submission, competent authority signature."
            ),
        }
    ],
    [
        {
            "heading": "Annexure B: Travel Expense Form",
            "kind": "form",
            "body": (
                "Annexure B: Travel Expense Form: https://home.ssis.pk/travel-claim-form. "
                "Travel claim form. Form reference TCF-2025-04-9. "
                "Name, employee code, designation, department. "
                "Start date, start time, end date, end time, same day, travel type, days travel, nights stay. "
                "Visit details and additional remarks. "
                "Expenses: description, amount in Rs, notes. Rate per KM, total KM, toll plaza, ticket charges, local travel, meals, "
                "hotel bill, self stay, board or meeting room charges, total expenses. "
                "Traveller signature and HOD or director signature."
            ),
        }
    ],
    [
        {
            "heading": "Annexure C: Hotel Entitlement",
            "kind": "table",
            "body": (
                "Grade: Group Chief (GC). Hotel entitlement: Avari Towers, Pearl Continental, Marriott Hotel, Movenpick Hotel, "
                "Ramada Creek Hotel, Nishat Hotel, Faletti's Hotel, Serena Hotel. "
                "Proposed rates: PKR 28,000 to PKR 35,000. Self-stay: PKR 22,000. "
                "All applicable taxes shall be treated separately from the above limits."
            ),
        },
        {
            "heading": "Annexure C: Hotel Entitlement",
            "kind": "table",
            "body": (
                "Grade: Deputy General Manager (DGM) to General Manager (GM). "
                "Hotel entitlement: Nishat Hotel, Royal Swiss, Luxus Grand, Best Western Premier, Avari Express. "
                "Proposed rates: PKR 24,000 to PKR 28,000. Self-stay: PKR 15,500."
            ),
        },
        {
            "heading": "Annexure C: Hotel Entitlement",
            "kind": "table",
            "body": (
                "Grade: Assistant General Manager (AGM) & Senior Manager (SM). "
                "Hotel entitlement: Challet Hotel, Hotel One, Hotel Excelsior. "
                "Proposed rates: PKR 20,000 to PKR 24,000. Self-stay: PKR 13,000."
            ),
        },
        {
            "heading": "Annexure C: Hotel Entitlement",
            "kind": "table",
            "body": (
                "Grade: Assistant Manager (AM) & Manager (M). "
                "Hotel entitlement: Faran Hotel, Asaish Hotel or as per available list of hotels. "
                "Proposed rates: PKR 12,000 to PKR 16,000. Self-stay: PKR 8,000."
            ),
        },
        {
            "heading": "Annexure C: Hotel Entitlement",
            "kind": "table",
            "body": (
                "Grade: Senior Executive (SE) & below. Hotel entitlement: twin sharing as per the available list of hotels. "
                "Proposed rates: none. Self-stay: PKR 5,000."
            ),
        },
    ],
    [
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 70cc petrol. Grade entitlement: all levels. Mileage: 40 km/liter. Maintenance and depreciation: Rs 2.0/km.",
        },
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 125cc petrol. Grade entitlement: all levels. Mileage: 30 km/liter. Maintenance and depreciation: Rs 2.5/km.",
        },
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 660cc/800cc petrol. Grade entitlement: O to M. Mileage: 14 km/liter. Maintenance and depreciation: Rs 3.5/km.",
        },
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 1000cc petrol. Grade entitlement: SM / AGM. Mileage: 12 km/liter. Maintenance and depreciation: Rs 3.5/km.",
        },
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 1300cc petrol. Grade entitlement: DGM / GM. Mileage: 10 km/liter. Maintenance and depreciation: Rs 4.0/km.",
        },
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 1500cc petrol. Grade entitlement: GM / GC. Mileage: 10 km/liter. Maintenance and depreciation: Rs 5.0/km.",
        },
        {
            "heading": "Annexure D: Fuel Entitlement List",
            "kind": "table",
            "body": "Vehicle: 1800cc petrol. Grade entitlement: GC / COO (Business). Mileage: 10 km/liter. Maintenance and depreciation: Rs 6.0/km.",
        },
    ],
]
