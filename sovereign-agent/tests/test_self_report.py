"""Tests for self-report-d — she answers questions about herself from her
real self-map + model roster, not generic LLM filler.
"""
from __future__ import annotations

import pytest

from sovereign_agent.self_report import compose_self_report, is_self_query


# ── detection ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    "what can you do?",
    "what models are you running?",
    "how are you wired?",
    "who are you?",
    "tell me about yourself",
    "what are your capabilities",
    "what tools do you have",
])
def test_self_questions_are_detected(q):
    assert is_self_query(q) is True


@pytest.mark.parametrize("q", [
    "what's the weather",
    "help me write a function",
    "summarize this document",
    "",
])
def test_ordinary_messages_are_not_hijacked(q):
    assert is_self_query(q) is False


# ── the composed answer is grounded, not filler ─────────────────────────
def test_report_identifies_her_as_a_local_sovereign_agent():
    r = compose_self_report("who are you?")
    assert "Aria" in r
    assert "local" in r.lower()
    assert "cloud" in r.lower()          # explicitly NOT a cloud service
    # NOT the generic filler she used to give
    assert "sophisticated AI" not in r


def test_report_states_real_grounded_counts():
    r = compose_self_report("what can you do?")
    # the real system has many sentinels/tools/channels — the report cites them
    import re
    assert re.search(r"\d+ sentinels", r)
    assert re.search(r"\d+ tools", r)
    assert re.search(r"\d+ memory channels", r)


def test_models_question_lists_real_models():
    r = compose_self_report("what models are you running?")
    assert "orchestrator" in r and "aria-orchestrator" in r
    assert "Ollama" in r                 # names the real runtime


def test_wiring_question_explains_architecture_plainly():
    r = compose_self_report("how are you wired?")
    assert "authority gate" in r.lower()
    assert "sentinel" in r.lower()
    assert "reversible" in r.lower()


def test_report_never_raises_and_always_returns_text():
    for q in ("who are you", "what tools do you have", "how are you built"):
        r = compose_self_report(q)
        assert isinstance(r, str) and len(r) > 50


# ── converse() routes a self-question to the real report ────────────────
@pytest.mark.asyncio
async def test_converse_intercepts_a_self_question():
    from sovereign_agent.conversation import converse
    turn = await converse("what models are you running?", allow_llm=False)
    assert turn.kind == "self-report"
    joined = " ".join(turn.messages)
    assert "Aria" in joined and "aria-orchestrator" in joined


@pytest.mark.asyncio
async def test_converse_leaves_ordinary_messages_alone():
    from sovereign_agent.conversation import converse
    turn = await converse("just saying hello", allow_llm=False)
    assert turn.kind != "self-report"
