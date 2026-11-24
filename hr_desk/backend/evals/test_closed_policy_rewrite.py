"""A closed policy is refused on what the person asked, not on words a model rewrite added."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

from app.models import ChunkDraft, Completion, Employee, PolicyDraft
from app.pipeline import Pipeline
from app.store_memory import MemoryStore

TODAY = date(2026, 11, 24)
STORE_MANAGER = Employee("store@stylo.example", "Test store manager", "store_manager")
QUESTION = "How many days do I have to reply to a show cause notice?"
SHOW_CAUSE = ("6.1.8. Initiation of Due Process. The employee shall reply to the Show Cause Letter within "
              "four days of receiving it. Without a reply, a second letter is issued.")
TRAVEL = ("3.2. Authorization of Travel. A dually signed travel request form must reach Administration via HR "
          "at least 7 days before travel. Trips at short notice need email approval from the competent authority.")


def _pipeline(normalized_search: str) -> Pipeline:
    llm = Mock()
    llm.moderate.return_value = False
    llm.classify.return_value = "allow"
    llm.split_topic_queries.return_value = []
    llm.personal_query.return_value = ("other", normalized_search)
    llm.answer.return_value = Completion("The employee has four days to reply to the show cause notice.", 10, 10)
    embedder = Mock()
    # Text that mentions travel lands near the travel passage, as the real embedding did.
    embedder.embed.side_effect = lambda queries: [[0.2, 1.0] if "travel" in q.lower() else [1.0, 0.2] for q in queries]
    pipeline = Pipeline(MemoryStore(), embedder, llm, today=lambda: TODAY)
    for id, title, audience, heading, body, vector in (
        ("cap", "Corrective Action Policy", "everyone", "6.1.8. Initiation of Due Process", SHOW_CAUSE,
         [1.0, 0.6]),
        ("travel", "Travel Policy", "officer,general_manager,hr", "3.2. Authorization of Travel", TRAVEL, [0.0, 1.0]),
    ):
        pipeline.store.insert_policy(PolicyDraft(id, title, audience, TODAY, None, body),
                                     [ChunkDraft(f"{title}, {heading}", heading, body, body)], [vector], as_of=TODAY)
    return pipeline


def test_a_rewrite_that_drags_in_a_closed_policy_does_not_refuse():
    drifted = ("What is the standard response timeline for a show cause notice within the business travel "
               "policy framework (including who approves, and any exceptions or extensions)?")
    result = _pipeline(drifted).ask(STORE_MANAGER, QUESTION)
    assert result.outcome == "answered", result.answer
    assert "four days" in result.answer


def test_a_question_about_the_closed_policy_is_still_refused():
    result = _pipeline("travel request form deadline").ask(
        STORE_MANAGER, "How many days before travel must I submit the travel request form?")
    assert result.outcome == "refused", result.answer
    assert "7 days" not in result.answer
