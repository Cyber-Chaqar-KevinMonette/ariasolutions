"""Integration test: narrate_intent actually fires from the real work loop.

Kevin, 2026-07-26: "I want her to be upfront about everything she plans
to do, is doing, and wants to do." test_work_narrator.py proves the
function's shape in isolation; this proves agent_session.py really
calls it at the start of every subtask, not just in theory.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _loop_result(final_message):
    from sovereign_agent.loop import LoopResult
    return LoopResult(ok=True, reason="complete", iterations=1,
                      tokens_used=10, final_message=final_message)


@pytest.mark.asyncio
async def test_narrate_intent_fires_before_the_subtask_runs():
    from sovereign_agent import agent_session
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget

    state = new_session(goal="write a haiku about the sea", mode=Mode.BUSY)

    intents: list[tuple[str, str]] = []

    def _fake_narrate_intent(session_id, description, **kwargs):
        intents.append((session_id, description))
        return True

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=lambda **kw: _loop_result("RESULT: done"))), \
         patch("sovereign_agent.work_narrator.narrate_intent",
               side_effect=_fake_narrate_intent):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=20, max_wall_seconds=120,
                             max_tokens=100_000),
            horizon_required=False,
        )

    assert len(intents) == 1
    sid, desc = intents[0]
    assert sid == state.session_id
    assert "haiku" in desc or "sea" in desc


@pytest.mark.asyncio
async def test_a_crashing_narrate_intent_never_breaks_the_session():
    from sovereign_agent.agent_session import SessionStore, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget

    state = new_session(goal="do a thing", mode=Mode.BUSY)

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=lambda **kw: _loop_result("RESULT: done"))), \
         patch("sovereign_agent.work_narrator.narrate_intent",
               side_effect=RuntimeError("no network")):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=20, max_wall_seconds=120,
                             max_tokens=100_000),
            horizon_required=False,
        )

    final = SessionStore().load(state.session_id)
    assert final.subtasks[0].status == "done"
