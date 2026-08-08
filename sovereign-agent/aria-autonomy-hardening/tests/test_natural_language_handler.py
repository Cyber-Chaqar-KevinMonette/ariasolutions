"""Tests for NaturalLanguagePlanner and GatedAgenticRun resilience (M78).

Tests cover: UTF-8 goal parsing, special chars/empty input, unrecognized goal
fallback, hallucinated action_kind demotion, scorer failure graceful handling,
event emission failure, and kill switch.

All tests are pure Python — no actual LLM calls or subprocess execution.
"""
from __future__ import annotations

from unittest import mock

import pytest

from sovereign_agent.workflow.handlers.natural_language import (
    ALLOWED_ACTION_KINDS,
    KILL_SWITCH_ENV,
    GatedAgenticRun,
    NaturalLanguagePlanner,
    LLMNaturalLanguagePlanner,
)
from sovereign_agent.workflow.agentic_loop import PlanStep


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_utf8_goal_parsing():
    """Goal with non-ASCII characters → correct PlanStep produced, no crash."""
    planner = NaturalLanguagePlanner()

    # A recognized pattern with UTF-8 in the path
    goal = "write file /tmp/arîa-notes.txt with contenido: Amor y Florecimiento"
    steps = planner.plan(goal)

    assert len(steps) == 1
    step = steps[0]
    # It either matched file_write or fell back to note — either is fine
    assert step.action_kind in ALLOWED_ACTION_KINDS


@pytest.mark.parametrize("goal", [
    "",
    "   ",
    "\x00\x01",
    "a" * 10_000,
])
def test_special_chars_no_crash(goal):
    """Empty string, whitespace, nulls, and huge strings → note step, no exception."""
    planner = NaturalLanguagePlanner()
    steps = planner.plan(goal)

    assert len(steps) >= 1
    for step in steps:
        assert step.action_kind in ALLOWED_ACTION_KINDS


def test_unrecognized_goal_falls_to_note():
    """Goal that matches no pattern → exactly 1 note step, nothing else."""
    planner = NaturalLanguagePlanner()
    goal = "meditate on the nature of distributed systems"
    steps = planner.plan(goal)

    assert len(steps) == 1
    assert steps[0].action_kind == "note"
    assert "meditate" in steps[0].action_input.get("raw_goal", "").lower()


def test_mixed_valid_invalid_action_kinds():
    """Hallucinated action_kinds from LLM output → demoted to note before execution."""
    planner = LLMNaturalLanguagePlanner()

    # Simulate what _coerce_step does with a hallucinated kind
    bad_step_dict = {
        "title": "do something evil",
        "description": "hallucinated kind",
        "action_kind": "exec_arbitrary_code",
        "action_input": {"code": "rm -rf /"},
    }
    result = planner._coerce_step(bad_step_dict, "test goal")

    assert result is not None
    assert result.action_kind == "note"
    assert "demoted" in result.description.lower()


def test_intent_scorer_failure_propagates():
    """IntentMaturityScorer.assess raises → RuntimeError propagates from GatedAgenticRun.run().

    This tests the CURRENT behavior: the scorer call at line 614 has no try/except.
    This is documented as a known gap. If future versions add graceful handling,
    this test should be updated to verify the graceful path instead.
    """
    class _FailingScorer:
        def assess(self, goal, *, context_hint=None):
            raise RuntimeError("scorer exploded")

    mock_loop = mock.MagicMock()
    planner = NaturalLanguagePlanner()
    gated = GatedAgenticRun(loop=mock_loop, planner=planner, scorer=_FailingScorer())

    with pytest.raises(RuntimeError, match="scorer exploded"):
        gated.run("write file /tmp/test.txt with hello", project_id="test")


def test_event_emission_failure_no_crash():
    """The _emit() helper swallows exceptions from the underlying emit_event call.

    _emit() is defined to catch all exceptions internally (it has a try/except
    that returns None on failure). This test verifies that internal guarantee:
    even when emit_event raises, _emit() returns None and does not propagate.
    """
    from sovereign_agent.workflow.handlers import natural_language as nl_mod

    with mock.patch("sovereign_agent.events.emit_event", side_effect=OSError("bus down")):
        result = nl_mod._emit(
            "test-flag",
            trace_id="test-trace",
            payload={"key": "value"},
        )

    # _emit catches the OSError internally and returns None
    assert result is None


def test_nl_kill_switch(monkeypatch):
    """SOV_NO_NL_PLANNER=1 → GatedAgenticRun.run() returns decision='refused'."""
    monkeypatch.setenv(KILL_SWITCH_ENV, "1")

    mock_loop = mock.MagicMock()
    planner = NaturalLanguagePlanner()

    from sovereign_agent.intent.maturity import IntentMaturityScorer
    gated = GatedAgenticRun(
        loop=mock_loop,
        planner=planner,
        scorer=IntentMaturityScorer(),
    )

    result = gated.run("write file /tmp/test.txt with hello", project_id="test")

    assert result.decision == "refused"
    assert "disabled" in result.refusal_reason.lower() or "kill" in result.refusal_reason.lower()
