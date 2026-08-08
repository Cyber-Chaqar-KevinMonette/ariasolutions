"""Tests for inbox-cadence-d — a structural nudge to keep Aria's inbox
empty during a work/auto session.

Kevin, 2026-07-26: "she needs to be emptying her inbox every 15 minutes
or so maybe... she should keep her inbox empty." Real mechanism: every
subtask boundary in `_execute_subtask` checks whether enough wall-clock
time has passed AND her inbox (direction=to_aria) is genuinely non-
empty, and if so auto-enqueues ONE subtask to read + close it out via
the new acknowledge_inbox_note tool. Never busywork on a clean inbox.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _loop_result(final_message):
    from sovereign_agent.loop import LoopResult
    return LoopResult(ok=True, reason="complete", iterations=1,
                      tokens_used=10, final_message=final_message)


@pytest.mark.asyncio
async def test_nudge_appends_a_subtask_when_inbox_is_non_empty():
    from sovereign_agent.agent_session import SessionStore, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore

    rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
    rs.tell_aria("please read this before building anything else")

    state = new_session(goal="do a thing", mode=Mode.BUSY)

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=lambda **kw: _loop_result("RESULT: done"))):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=20, max_wall_seconds=120,
                             max_tokens=100_000),
            horizon_required=False,
        )

    final = SessionStore().load(state.session_id)
    descs = [s.description for s in final.subtasks]
    assert any("read_inbox" in d and "acknowledge_inbox_note" in d for d in descs), descs


@pytest.mark.asyncio
async def test_no_nudge_when_inbox_is_already_empty():
    from sovereign_agent.agent_session import SessionStore, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget

    state = new_session(goal="do a thing", mode=Mode.BUSY)

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=lambda **kw: _loop_result("RESULT: done"))):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=20, max_wall_seconds=120,
                             max_tokens=100_000),
            horizon_required=False,
        )

    final = SessionStore().load(state.session_id)
    descs = [s.description for s in final.subtasks]
    assert not any("acknowledge_inbox_note" in d for d in descs)
    assert len(final.subtasks) == 1  # nothing extra appended


@pytest.mark.asyncio
async def test_nudge_does_not_repeat_within_the_cadence_window(monkeypatch):
    """Two subtasks complete back-to-back (well under 15 real minutes
    apart) — only ONE nudge should have been enqueued, not one per
    boundary."""
    from sovereign_agent import agent_session
    from sovereign_agent.agent_session import SessionStore, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore

    monkeypatch.setattr(agent_session, "INBOX_CADENCE_S", 900.0)

    rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
    rs.tell_aria("a note")

    state = new_session(goal="do a thing", mode=Mode.BUSY)

    calls = {"n": 0}

    async def _fake(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _loop_result("RESULT: step one done\n"
                                "NEXT_SUBTASK[tier=1]: a second real step\n")
        return _loop_result("RESULT: done")

    with patch("sovereign_agent.agent_session.agent_loop",
               new=AsyncMock(side_effect=_fake)):
        await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=20, max_wall_seconds=120,
                             max_tokens=100_000),
            horizon_required=False,
        )

    final = SessionStore().load(state.session_id)
    nudges = [s for s in final.subtasks if "acknowledge_inbox_note" in s.description]
    assert len(nudges) == 1
