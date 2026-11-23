"""A numbered point stays that point, and a named policy stays that policy."""

from datetime import date

from app.clauses import asked_page, extract_clause, focus_clauses, heading_has_phrase, heading_phrases
from app.models import Passage
from app.retrieve import search_passages

BODY = (
    "3.1.1. All Travel bookings will be made through the Administration Department.\n"
    "3.1.5. Notify the employee once travel and accommodation arrangements are confirmed "
    "and provide them with all relevant documents.\n"
    "3.1.6. The Administration Department should verify the bill.\n"
    "3.2.1. All business travel must be pre-approved."
)


def _passage(title: str, body: str, heading: str = "3.1. Bookings and Record Keeping") -> Passage:
    return Passage(
        id=title,
        policy_id=title,
        title=title,
        section_label=f"{title}, {heading}",
        heading=heading,
        body=body,
        audience="everyone",
        effective_from=date(2025, 4, 15),
        effective_to=None,
    )


def test_a_subheading_does_not_include_the_points_around_it():
    text = extract_clause(BODY, "3.1.5")
    assert text.startswith("3.1.5. Notify the employee")
    assert "3.1.1" not in text
    assert "3.1.6" not in text
    assert "3.2.1" not in text


def test_a_heading_includes_its_subheadings_only():
    text = extract_clause(BODY, "3.1")
    assert "3.1.5. Notify the employee" in text
    assert "3.1.1. All Travel bookings" in text
    assert "3.2.1" not in text


def test_a_named_policy_drops_the_other_policy():
    travel = _passage("Travel Policy", BODY)
    medical = _passage(
        "Medical Insurance Policy",
        "3.1.5. Hospital care is covered for an overnight stay.",
        "3.1. In-Patient Medical Support",
    )
    question = "give me a short summary on point 3.1.5 in the travel policy"
    focused = focus_clauses([travel, medical], question)
    assert len(focused) == 1
    assert focused[0].title == "Travel Policy"
    assert "Hospital care" not in focused[0].body
    assert "3.1.6" not in focused[0].body


def test_an_unnamed_point_keeps_each_matching_policy_and_nothing_else():
    travel = _passage("Travel Policy", BODY)
    medical = _passage(
        "Medical Insurance Policy",
        "3.1.5. Hospital care is covered for an overnight stay.",
    )
    other = _passage("Code of Conduct", "Dress neatly at work.", "Dress code")
    focused = focus_clauses([travel, medical, other], "give me a short summary on point 3.1.5")
    assert {item.title for item in focused} == {"Travel Policy", "Medical Insurance Policy"}
    assert all("3.1.6" not in item.body for item in focused)


class _Store:
    def __init__(self, passages):
        self.passages = passages

    def candidates(self, embedding, query, audiences, today, limit):
        return list(self.passages)

    def clause_hits(self, numbers, audiences, today):
        return list(self.passages)


def test_summary_wording_does_not_hide_the_numbered_point():
    clause = _passage("Travel Policy", BODY)
    clause.vec_score = 0.2
    distractor = _passage("Code of Conduct", "This summary covers the dress code point for every section.")
    distractor.vec_score = 0.8
    distractor.id = "conduct"
    found = search_passages(_Store([distractor, clause]), [0.0], "give me a short summary on point 3.1.5", {"everyone"}, date(2026, 11, 17))
    assert found[0].title == "Travel Policy"


def test_a_named_title_is_found_even_when_search_misses_it():
    annexure = _passage("Travel Policy", "Annexure C. Grade: Group Chief (GC).", "Annexure C")
    annexure.vec_score = 0.1
    annexure.id = "annexure-c"
    other = _passage("Code of Conduct", "Dress neatly at work.", "Dress code")
    other.vec_score = 0.9
    other.id = "conduct"

    class _Titles(_Store):
        def heading_hits(self, phrases, audiences, today):
            return [annexure]

    found = search_passages(_Titles([other]), [0.0], "show me annexure c", {"everyone"}, date(2026, 11, 17))
    assert found[0].heading == "Annexure C"
    assert asked_page("what is on page 7") == 7
    assert "annexure c" in heading_phrases("show me annexure c")
    assert "km coverage" in heading_phrases("what does km coverage mean")
    assert "ceo" in heading_phrases("ceo")
    assert heading_has_phrase("Message from the CEO", "message ceo")
    assert not heading_has_phrase("COO, Director, CEO, CFO", "message ceo")
