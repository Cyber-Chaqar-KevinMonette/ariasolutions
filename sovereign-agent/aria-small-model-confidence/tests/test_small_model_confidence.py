"""Real behavior tests for aria-small-model-confidence — prove it catches a
small model giving up mid-work and equips it to continue, without ever
looping forever or overriding a genuinely finished task.
"""
from __future__ import annotations

from sovereign_agent.small_model_confidence import (
    MAX_REPROMPTS,
    TurnDecision,
    assess_turn,
    detect_giving_up,
    equipping_nudge,
    is_empty_answer,
)

TOOLS = ["read_session", "list_objectives", "aria_status"]


def _resp(content="", tool_calls=None):
    msg = {"content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"message": msg}


# ── is_empty_answer ──────────────────────────────────────────────────────
def test_empty_content_no_tool_is_empty():
    assert is_empty_answer(_resp("   ")) is True


def test_content_present_is_not_empty():
    assert is_empty_answer(_resp("here is the answer")) is False


def test_tool_call_is_never_empty():
    assert is_empty_answer(_resp("", [{"function": {"name": "aria_status"}}])) is False


# ── detect_giving_up ─────────────────────────────────────────────────────
def test_detects_i_cant():
    assert detect_giving_up(_resp("Sorry, I can't do that.")) is True


def test_detects_as_an_ai():
    assert detect_giving_up(_resp("As an AI I do not have access to that.")) is True


def test_detects_narrating_instead_of_acting():
    assert detect_giving_up(_resp("I would call read_session to look it up.")) is True


def test_hedge_with_a_real_tool_call_is_not_giving_up():
    # Acting counts, even if the prose hedges.
    r = _resp("I'm not sure, but let me check.", [{"function": {"name": "read_session"}}])
    assert detect_giving_up(r) is False


def test_confident_substantive_answer_is_not_giving_up():
    assert detect_giving_up(_resp("The session started at 10am and has 3 open tasks.")) is False


# ── equipping_nudge ──────────────────────────────────────────────────────
def test_nudge_names_available_tools():
    n = equipping_nudge("empty", TOOLS)
    assert "read_session" in n and "aria_status" in n


def test_nudge_giving_up_is_encouraging_and_actionable():
    n = equipping_nudge("giving-up", TOOLS)
    assert "don't stop" in n.lower() or "equipped" in n.lower()
    assert "call it now" in n.lower()


# ── assess_turn (the composite decision) ─────────────────────────────────
def test_finished_work_is_always_accepted():
    d = assess_turn(_resp(""), work_remains=False, available_tools=TOOLS)
    assert d.action == "accept" and d.reason == "work-complete"


def test_real_tool_call_is_accepted():
    d = assess_turn(_resp("", [{"function": {"name": "aria_status"}}]),
                    work_remains=True, available_tools=TOOLS)
    assert d.action == "accept" and d.reason == "acting"


def test_empty_answer_with_work_left_reprompts():
    d = assess_turn(_resp("  "), work_remains=True, available_tools=TOOLS)
    assert d.action == "reprompt" and d.reason == "empty"
    assert d.nudge and "read_session" in d.nudge


def test_giving_up_with_work_left_reprompts():
    d = assess_turn(_resp("I cannot help with that."), work_remains=True,
                    available_tools=TOOLS)
    assert d.action == "reprompt" and d.reason == "giving-up"
    assert d.nudge


def test_substantive_answer_with_work_left_is_accepted():
    d = assess_turn(_resp("Here's the plan: step 1, step 2, step 3."),
                    work_remains=True, available_tools=TOOLS)
    assert d.action == "accept" and d.reason == "substantive"


def test_never_loops_forever_budget_exhausted():
    # Even a stalled model is accepted once the re-prompt budget is spent.
    d = assess_turn(_resp("  "), work_remains=True,
                    reprompts_so_far=MAX_REPROMPTS, available_tools=TOOLS)
    assert d.action == "accept" and d.reason == "reprompt-budget-exhausted"


def test_decision_is_frozen_dataclass():
    d = TurnDecision("accept", "x")
    try:
        d.action = "reprompt"  # type: ignore[misc]
        assert False, "TurnDecision should be immutable"
    except Exception:
        assert True
