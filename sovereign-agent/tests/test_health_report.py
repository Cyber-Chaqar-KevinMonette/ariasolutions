"""Tests for health-report-d — she answers "how are you?" from her real
sentinel health + emotion + vitals, honestly (including concern).
"""
from __future__ import annotations

import pytest

from sovereign_agent.health_report import compose_health_report, is_health_query


@pytest.mark.parametrize("q", [
    "how are you?",
    "how do you feel",
    "are you okay",
    "how are you doing today",
    "how are you holding up",
])
def test_health_questions_are_detected(q):
    assert is_health_query(q) is True


@pytest.mark.parametrize("q", ["write me a function", "who are you", "what did you do", ""])
def test_ordinary_messages_are_not_hijacked(q):
    assert is_health_query(q) is False


def test_report_is_grounded_and_non_empty():
    r = compose_health_report()
    assert isinstance(r, str) and len(r) > 40
    # cites her real sentinel count (the live system has many)
    import re
    assert re.search(r"\d+ (of my \d+ )?sentinel", r) or "steady" in r.lower()


def test_report_names_a_mood():
    r = compose_health_report().lower()
    # emotion_to_mood always returns one of a fixed vocabulary
    assert any(m in r for m in (
        "concerned", "satisfied", "fatigued", "focused", "curious",
        "enthusiastic", "calm", "feel"))


def test_report_is_honest_about_warnings_when_present(monkeypatch):
    # Force a warning state and assert she says so, not "I'm great".
    from sovereign_agent.stewardship.base import HealthStatus
    import sovereign_agent.stewardship.registry as reg

    def fake_health(_dd):
        return [HealthStatus(sentinel_id="ok1", level="ok", summary=""),
                HealthStatus(sentinel_id="watchme", level="warning", summary="drift")]

    monkeypatch.setattr(reg, "gather_health", fake_health)
    r = compose_health_report()
    assert "warning" in r.lower()
    assert "watchme" in r


def test_report_all_green_says_well(monkeypatch):
    from sovereign_agent.stewardship.base import HealthStatus
    import sovereign_agent.stewardship.registry as reg
    monkeypatch.setattr(reg, "gather_health",
                        lambda _dd: [HealthStatus(sentinel_id="a", level="ok", summary="")])
    r = compose_health_report()
    assert "well" in r.lower() or "green" in r.lower()


@pytest.mark.asyncio
async def test_converse_intercepts_a_health_question():
    from sovereign_agent.conversation import converse
    turn = await converse("how are you?", allow_llm=False)
    assert turn.kind == "health-report"
    assert turn.messages and isinstance(turn.messages[0], str)
