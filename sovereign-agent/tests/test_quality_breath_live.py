"""Behavior tests for aria-quality-breath, promoted to live tests/."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _mk_state():
    from sovereign_agent.agent_session import new_session
    from sovereign_agent.modes import Mode

    return new_session(goal="a modest goal", mode=Mode.BUSY)


def test_compact_guidance_is_the_default_and_small():
    from sovereign_agent.agent_session import _format_session_guidance

    state = _mk_state()
    g = _format_session_guidance(state, state.subtasks[0])
    assert len(g) < 700, f"compact guidance too big: {len(g)}"
    assert "RESULT:" in g and "NEXT_SUBTASK" in g  # protocols survive, terse
    assert "HOW TO GROW THE QUEUE" not in g        # the heavy section is gone


def test_kill_switch_restores_the_full_template(monkeypatch):
    from sovereign_agent.agent_session import _format_session_guidance

    monkeypatch.setenv("SOV_NO_GUIDANCE_DIET", "1")
    state = _mk_state()
    g = _format_session_guidance(state, state.subtasks[0])
    assert "HOW TO GROW THE QUEUE" in g  # the original, byte-for-byte path


def test_scope_contract_rides_the_compact_guidance():
    from sovereign_agent.agent_session import _format_session_guidance
    from sovereign_agent.scope import ScopeContract, save_scope

    state = _mk_state()
    save_scope(state.session_id, ScopeContract(goal="g", out_of_scope=["the attic"]))
    g = _format_session_guidance(state, state.subtasks[0])
    assert "SCOPE CONTRACT" in g and "the attic" in g


@pytest.mark.asyncio
async def test_engine_protocols_still_parse_end_to_end():
    """The diet must not break RESULT/NEXT_SUBTASK parsing."""
    from sovereign_agent.agent_session import SessionStore, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget

    state = _mk_state()
    calls = {"n": 0}

    async def _fake(**kw):
        calls["n"] += 1
        assert "RESULT:" in kw["goal"]  # compact guidance reached the loop
        if calls["n"] == 1:
            return LoopResult(ok=True, reason="complete", iterations=1, tokens_used=1,
                              final_message="RESULT: step done\nNEXT_SUBTASK[tier=1]: one more\n")
        return LoopResult(ok=True, reason="complete", iterations=1, tokens_used=1,
                          final_message="RESULT: all done")

    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        r = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=10, max_wall_seconds=60, max_tokens=50_000),
            horizon_required=False,
        )
    assert r.status == "complete"
    final = SessionStore().load(state.session_id)
    assert final.progress() == (2, 2)
    assert any(s.result_summary == "step done" for s in final.subtasks)
