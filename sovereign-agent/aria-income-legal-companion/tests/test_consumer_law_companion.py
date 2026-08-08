"""Tests for consumer_law_companion.py."""
from __future__ import annotations

from sovereign_agent.consumer_law_companion import (
    DISCLAIMER, TOPICS, answer_consumer_law_question)


def test_debt_collection_question_routes_to_fdcpa():
    ans = answer_consumer_law_question("A debt collector keeps calling me at work")
    assert ans.topic == "Debt collection"
    assert "FDCPA" in ans.statute
    assert "consumerfinance.gov" in " ".join(ans.sources)


def test_credit_report_question_routes_to_fcra():
    ans = answer_consumer_law_question("How do I dispute an error on my credit report?")
    assert ans.topic == "Credit reporting"
    assert "FCRA" in ans.statute


def test_billing_dispute_question_routes_to_fcba():
    ans = answer_consumer_law_question("There's an unauthorized charge on my credit card")
    assert ans.topic == "Credit card billing disputes"
    assert "FCBA" in ans.statute


def test_unmatched_question_still_gets_a_real_useful_answer():
    ans = answer_consumer_law_question("what is a widget")
    assert ans.topic == "General consumer protection"
    assert ans.sources  # never empty


def test_every_answer_carries_the_disclaimer():
    for q in ("debt collector", "credit report", "apr", "billing error",
             "credit discrimination", "totally unrelated question"):
        ans = answer_consumer_law_question(q)
        assert ans.disclaimer == DISCLAIMER
        assert "not legal advice" in ans.as_text().lower()


def test_empty_question_gets_fallback_not_a_crash():
    ans = answer_consumer_law_question("")
    assert ans.topic == "General consumer protection"


def test_every_topic_has_a_real_source_url():
    for topic in TOPICS:
        assert topic.sources
        for url in topic.sources:
            assert url.startswith("https://")
            assert "consumerfinance.gov" in url or "ftc.gov" in url


def test_as_text_is_well_formed():
    ans = answer_consumer_law_question("debt collector called me")
    text = ans.as_text()
    assert "Debt collection" in text
    assert "Sources:" in text
    assert "⚖️" in text
