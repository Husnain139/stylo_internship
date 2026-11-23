from datetime import date

import pymupdf

from app.models import Passage
from app.pipeline import _citation
from app.source_page import source_page_url


def test_a_pdf_page_is_attached_to_the_policy_text(tmp_path, monkeypatch):
    pdf = tmp_path / "medical.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "In-Patient Benefit Entitlement Schedule")
    document.save(pdf)
    document.close()
    monkeypatch.setattr("app.source_page._source_file", lambda policy_id: pdf)
    monkeypatch.setattr("app.source_page._MEDIA", tmp_path / "media")

    passage = Passage(
        id="doc-1:0",
        policy_id="doc-1234567890abcdef",
        title="Medical Insurance Policy",
        section_label="Medical Insurance Policy, In-Patient Benefit Entitlement Schedule",
        heading="In-Patient Benefit Entitlement Schedule",
        body="Plan rows are on this page.",
        audience="everyone",
        effective_from=date(2024, 6, 1),
        effective_to=None,
        page=1,
    )
    url = source_page_url(passage)
    assert url == "/api/media/doc-1234567890abcdef/page-1.png"
    assert (tmp_path / "media" / "doc-1234567890abcdef" / "page-1.png").is_file()
    assert _citation(passage, include_full_page=True).image == url
    assert _citation(passage).image == ""


def test_the_page_with_the_passage_wins_over_a_repeated_title(tmp_path, monkeypatch):
    pdf = tmp_path / "policy.pdf"
    document = pymupdf.open()
    cover = document.new_page()
    cover.insert_text((72, 72), "Corrective Action Policy")
    inside = document.new_page()
    inside.insert_text((72, 72), "Corrective Action Policy")
    inside.insert_text((72, 120), "Show cause notice is issued by the line manager.")
    document.save(pdf)
    document.close()
    monkeypatch.setattr("app.source_page._source_file", lambda policy_id: pdf)
    monkeypatch.setattr("app.source_page._MEDIA", tmp_path / "media")
    from app.source_page import _find_page

    assert _find_page(pdf, "Corrective Action Policy", "Show cause notice is issued by the line manager.") == 1
