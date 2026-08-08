"""Behavior tests for aria-session-bridge, promoted to live tests/ — the
REAL, already-patched modules. Plain imports, no shadow copy. The engine
itself is mocked where a real model would be needed; every SAFETY property
is tested against the real code paths.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ── the queue (Kevin's no-interrupt rule) ─────────────────────────────────


def test_queue_and_drain_round_trip():
    from sovereign_agent.session_bridge import (
        drain_operator_messages, queue_operator_message,
    )

    queue_operator_message("remember to check the lighthouse")
    queue_operator_message("also water the plants")
    notes = drain_operator_messages()
    assert "remember to check the lighthouse" in notes
    assert "also water the plants" in notes
    # drained = answered — a second drain returns nothing
    assert drain_operator_messages() == []


def test_drain_leaves_untagged_inbox_notes_alone():
    """Notes left via `sov requests tell` (no QUEUE_TAG) must stay open for
    ReadInboxTool exactly as before."""
    from sovereign_agent.session_bridge import _request_store, drain_operator_messages
    from sovereign_agent.workflow.requests import DIRECTION_TO_ARIA

    store = _request_store()
    store.open("note", "a standing note", body="left via sov requests tell",
               direction=DIRECTION_TO_ARIA)
    assert drain_operator_messages() == []
    open_titles = [r.title for r in store.list_open(direction=DIRECTION_TO_ARIA)]
    assert "a standing note" in open_titles


def test_drain_never_raises_on_broken_store(monkeypatch):
    from sovereign_agent import session_bridge

    monkeypatch.setattr(session_bridge, "_request_store",
                        lambda: (_ for _ in ()).throw(RuntimeError("db gone")))
    assert session_bridge.drain_operator_messages() == []


# ── boundary delivery inside the engine ───────────────────────────────────


@pytest.mark.asyncio
async def test_queued_messages_fold_into_the_subtask_goal():
    """The delivery side: a queued message appears in the composed goal the
    inner agent_loop receives at the NEXT subtask start — a safe boundary."""
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.session_bridge import queue_operator_message

    queue_operator_message("please prefer the gentle approach")

    seen_goals: list[str] = []

    async def _fake_loop(**kwargs):
        seen_goals.append(kwargs["goal"])
        from sovereign_agent.loop import LoopResult

        return LoopResult(ok=True, reason="complete", iterations=1,
                          tokens_used=10, final_message="RESULT: done")

    state = new_session(goal="a tiny goal", mode=Mode.BUSY)
    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake_loop)):
        result = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=10, max_wall_seconds=60, max_tokens=10_000),
            horizon_required=False,
        )
    assert result.status == "complete"
    assert seen_goals, "the inner loop never ran"
    assert "please prefer the gentle approach" in seen_goals[0]
    assert "OPERATOR MESSAGES" in seen_goals[0]


# ── start_goal_session ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_goal_session_runs_the_real_engine_shape():
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.session_bridge import start_goal_session

    fake = AsyncMock(return_value=LoopResult(
        ok=True, reason="complete", iterations=2, tokens_used=50,
        final_message="RESULT: all done",
    ))
    with patch("sovereign_agent.agent_session.agent_loop", new=fake):
        result = await start_goal_session("do a small kindness")
    assert result.status == "complete"
    assert result.completed_subtasks == result.total_subtasks == 1


@pytest.mark.asyncio
async def test_budget_carries_the_safety_margin():
    """The bridge composes Workstream N's design: a wall budget WITH a real
    safety margin rides into run_session."""
    import sovereign_agent.session_bridge as sb
    from sovereign_agent.modes import RunBudget

    captured = {}

    async def _capture_run_session(**kwargs):
        captured["budget"] = kwargs["budget"]
        from sovereign_agent.agent_session import SessionResult

        return SessionResult(session_id="x", status="complete",
                             completed_subtasks=1, total_subtasks=1,
                             total_iterations=1, total_tokens=1,
                             elapsed_seconds=0.1)

    with patch("sovereign_agent.agent_session.run_session",
               new=AsyncMock(side_effect=_capture_run_session)):
        await sb.start_goal_session("g", wall_seconds=3600, safety_margin_seconds=360)
    b: RunBudget = captured["budget"]
    assert b.max_wall_seconds == 3600
    assert b.safety_margin_seconds == 360


# ── the cockpit (safety properties) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_mode_work_verb_proposes_and_never_runs():
    """THE gate property: in chat mode, /work proposes and waits — the
    engine is never invoked."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        ran = []
        app._run_work_session_worker = lambda goal: ran.append(goal)
        app._start_work_session("refactor everything")
        await pilot.pause()
        assert ran == [], "chat mode auto-ran an autonomous session!"
        assert app._session_running is False
        text = "\n".join(getattr(l, "text", str(l)) for l in app._chat_log.lines)
        assert "proposed, waiting" in text


@pytest.mark.asyncio
async def test_work_mode_runs_the_session():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit_modes import CockpitMode, set_mode

    set_mode(CockpitMode.WORK)
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        ran = []
        app._run_work_session_worker = lambda goal: ran.append(goal)
        app._start_work_session("a real goal")
        await pilot.pause()
        assert ran == ["a real goal"]
        assert app._session_running is True


@pytest.mark.asyncio
async def test_typing_during_a_session_queues_not_drops():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.session_bridge import drain_operator_messages

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        app._session_running = True
        app._dispatch_turn("a mid-run thought from kevin")
        await pilot.pause()
        text = "\n".join(getattr(l, "text", str(l)) for l in app._chat_log.lines)
        assert "queued for her next safe checkpoint" in text
    assert "a mid-run thought from kevin" in drain_operator_messages()


@pytest.mark.asyncio
async def test_busy_ordinary_turn_keeps_old_behavior():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        app._session_running = False
        app._dispatch_turn("hello?")
        await pilot.pause()
        text = "\n".join(getattr(l, "text", str(l)) for l in app._chat_log.lines)
        assert "aria is still working" in text


@pytest.mark.asyncio
async def test_halt_verb_bypasses_the_queue():
    """Safety outranks politeness: /halt is a slash verb — it never routes
    through _dispatch_turn's queue branch."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._session_running = True
        halted = []
        app.action_halt = lambda: halted.append(True)
        app._handle_slash("/halt")
        assert halted == [True]


@pytest.mark.asyncio
async def test_small_wall_never_yields_zero_effective_limit():
    """Regression from the first live E2E: a margin larger than the wall
    made effective_wall_limit 0 and tripped the budget instantly. The
    bridge clamps to N's design (10% of wall, 60s floor)."""
    import sovereign_agent.session_bridge as sb

    captured = {}

    async def _capture(**kwargs):
        captured["budget"] = kwargs["budget"]
        from sovereign_agent.agent_session import SessionResult

        return SessionResult(session_id="x", status="complete",
                             completed_subtasks=1, total_subtasks=1,
                             total_iterations=1, total_tokens=1,
                             elapsed_seconds=0.1)

    with patch("sovereign_agent.agent_session.run_session",
               new=AsyncMock(side_effect=_capture)):
        await sb.start_goal_session("g", wall_seconds=180)
    from sovereign_agent.modes import effective_wall_limit

    b = captured["budget"]
    assert effective_wall_limit(b) > 0
    assert b.safety_margin_seconds <= 60
