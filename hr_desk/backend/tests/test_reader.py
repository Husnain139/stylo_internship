"""Admin add and replace use this reader, so these checks guard the next upload."""

from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document

from app.passages import policy_from_bytes

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "data" / "policies"


def test_word_policy_keeps_nested_table_values():
    document = Document()
    document.add_heading("Allowance", 1)
    outer = document.add_table(rows=1, cols=1)
    outer.cell(0, 0).text = "Eligibility details"
    nested = outer.cell(0, 0).add_table(rows=2, cols=2)
    nested.cell(0, 0).text, nested.cell(0, 1).text = "Role", "Amount"
    nested.cell(1, 0).text, nested.cell(1, 1).text = "Analyst", "PKR 27000"
    buffer = BytesIO()
    document.save(buffer)

    draft = policy_from_bytes("Allowance.docx", buffer.getvalue())
    assert any(chunk.content_type == "table" and "PKR 27000" in chunk.body
               and "Nested table" in chunk.heading_path for chunk in draft.chunks)


def test_mixed_and_scanned_pdf_pages_keep_ocr_text(monkeypatch):
    attempts = []

    def read_page(page, *, language, dpi, full):
        attempts.append((page.number, full))
        page.insert_text((72, 240), f"Scanned instructions for packet {page.number + 1}.")
        return page.get_textpage()

    monkeypatch.setattr(pymupdf.Page, "get_textpage_ocr", read_page)
    picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 12, 12), 0)
    picture.clear_with(255)
    with pymupdf.open() as document:
        mixed = document.new_page()
        mixed.insert_text((72, 72), "Native checklist text for employees.")
        mixed.insert_image(pymupdf.Rect(72, 100, 180, 180), stream=picture.tobytes("png"))
        scanned = document.new_page()
        scanned.insert_image(pymupdf.Rect(72, 100, 180, 180), stream=picture.tobytes("png"))
        data = document.tobytes()

    draft = policy_from_bytes("Mixed packet.pdf", data)
    text = "\n".join(chunk.body for chunk in draft.chunks)
    assert "Native checklist text" in text
    assert "Scanned instructions for packet 1" in text
    assert "Scanned instructions for packet 2" in text
    assert attempts == [(0, False), (1, True)]


def test_a_blank_scan_is_not_stored_as_the_travel_policy():
    document = pymupdf.open()
    document.new_page()
    draft = policy_from_bytes("New Scan.pdf", document.tobytes())
    assert draft is None


def test_replacing_the_office_files_keeps_the_reader_improvements():
    travel = policy_from_bytes(
        "Travel Policy - Stylo May-2025.pdf",
        (POLICIES / "Travel Policy - Stylo May-2025.pdf").read_bytes(),
    )
    medical = policy_from_bytes(
        "Medical Takaful Policy 051124.pdf",
        (POLICIES / "Medical Takaful Policy 051124.pdf").read_bytes(),
    )
    provident_name = next(POLICIES.glob("Provident*.docx")).name
    provident = policy_from_bytes(provident_name, (POLICIES / provident_name).read_bytes())
    advance = policy_from_bytes(
        "User Guidelines - Advance Salary (HO - RSC).docx",
        (POLICIES / "User Guidelines - Advance Salary (HO - RSC).docx").read_bytes(),
    )
    travel_text = "\n".join(chunk.body for chunk in travel.chunks)
    medical_text = "\n".join(chunk.body for chunk in medical.chunks)
    provident_text = "\n".join(f"{chunk.heading}\n{chunk.body}" for chunk in provident.chunks)
    advance_text = "\n".join(chunk.body for chunk in advance.chunks)

    assert travel.source_name == "Travel Policy - Stylo May-2025.pdf"
    assert "3.1.7. The Finance Department will ensure the bill is processed" in travel_text
    assert "https://home.ssis.pk/travel-claim-form" in travel_text
    assert "https://home.ssis.pk/travel-request-form" in travel_text
    assert "Annexures" in travel_text
    assert "Annexure C" in travel_text
    assert "KM Coverage" in travel_text
    assert "New Rates" in travel_text
    assert "Date of Signature: 14/4/25" in travel_text
    assert "Page 7 of 10" in travel_text
    assert "Stylo (Pvt.) Ltd. - HR Policy Manual" in travel_text
    assert "https://www.jubileelife.com/wp-content/uploads/2020/12/Consolidated-PPN-02-12-2020.pdf" in medical_text
    assert "Treatment of mental illness" in medical_text
    assert "In-Patient Benefit Entitlement Schedule" in medical_text
    assert "Annual In-Patient Health" in medical_text
    assert "Annexure D: In-Patient Claim Form and Required Documents" in medical_text
    assert "DOCUMENT CODE: HR-PM-001" in medical_text
    assert "Page 1 of 10" in medical_text
    assert "Code - HRP/0120/1" in provident_text
    assert "http://ess.stylo.pk/Default.aspx" in advance_text
