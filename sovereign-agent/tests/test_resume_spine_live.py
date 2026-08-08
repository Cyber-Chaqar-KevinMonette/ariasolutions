"""Behavior tests for aria-resume-spine, promoted to live tests/."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _loop_result(msg):
    from sovereign_agent.loop import LoopResult

    return LoopResult(ok=True, reason="complete", iterations=1,
                      tokens_used=10, final_message=msg)


@pytest.mark.asyncio
async def test_budget_paused_session_resumes_and_completes():
    """THE spine: a session that hit its budget resumes on the SAME id and
    finishes the remaining subtasks — scope + store intact."""
    from sovereign_agent.agent_session import SessionStore, Subtask, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.session_bridge import resume_goal_session

    state = new_session(goal="two step goal", mode=Mode.BUSY, initial_subtasks=[
        Subtask(id="st_a", description="step one", required_tier=1),
        Subtask(id="st_b", description="step two", required_tier=1),
    ])

    async def _fake(**kwargs):
        return _loop_result("RESULT: did a step")

    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        # An impossible budget: margin clamp floor (60s) vs 1s wall → trips
        r1 = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            budget=RunBudget(max_iterations=1, max_wall_seconds=3600,
                             max_tokens=100_000),
            horizon_required=False,
        )
        assert r1.status == "budget"  # iterations budget after step one
        mid = SessionStore().load(state.session_id)
        assert any(s.status == "pending" for s in mid.subtasks)

        r2 = await resume_goal_session(state.session_id)
        assert r2.session_id == state.session_id
        assert r2.status == "complete"
    final = SessionStore().load(state.session_id)
    assert all(s.status == "done" for s in final.subtasks)


@pytest.mark.asyncio
async def test_message_queued_during_pause_delivers_on_resume():
    from sovereign_agent.agent_session import new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.session_bridge import queue_operator_message, resume_goal_session

    state = new_session(goal="g", mode=Mode.BUSY)
    seen = []

    async def _fake(**kwargs):
        seen.append(kwargs["goal"])
        return _loop_result("RESULT: ok")

    queue_operator_message("a thought from the pause window")
    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        r = await resume_goal_session(state.session_id)
    assert r.status == "complete"
    assert "a thought from the pause window" in seen[0]


def test_resumable_sessions_lists_pending_work_only():
    from sovereign_agent.agent_session import SessionStore, new_session
    from sovereign_agent.modes import Mode
    from sovereign_agent.session_bridge import resumable_sessions

    store = SessionStore()
    s1 = new_session(goal="left behind", mode=Mode.BUSY)
    s1.status = "budget"
    store.save(s1)
    s2 = new_session(goal="finished", mode=Mode.BUSY)
    s2.subtasks[0].status = "done"
    s2.status = "complete"
    store.save(s2)
    ids = [s.session_id for s in resumable_sessions()]
    assert s1.session_id in ids
    assert s2.session_id not in ids


def test_resumable_sessions_includes_orphaned_in_progress_subtask():
    """resume-orphan-recovery-d: an abrupt exit (Ctrl+Q killed mid-subtask,
    before the exit-path fix) leaves status="active" with its one subtask
    stuck "in_progress" — no "pending" subtask at all. Before the fix, this
    silently vanished from the menu; it must now still show up."""
    from sovereign_agent.agent_session import SessionStore, new_session
    from sovereign_agent.modes import Mode
    from sovereign_agent.session_bridge import resumable_sessions

    store = SessionStore()
    s = new_session(goal="killed mid-flight", mode=Mode.BUSY)
    s.status = "active"
    s.subtasks[0].status = "in_progress"
    store.save(s)
    ids = [sess.session_id for sess in resumable_sessions()]
    assert s.session_id in ids


@pytest.mark.asyncio
async def test_orphaned_in_progress_subtask_reruns_on_resume():
    """resume-orphan-recovery-d: run_session must requeue (not permanently
    skip) a subtask left "in_progress" by a prior abrupt exit — otherwise
    /resume silently drops the exact work that was interrupted."""
    from sovereign_agent.agent_session import SessionStore, Subtask, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode

    state = new_session(goal="orphan test", mode=Mode.BUSY, initial_subtasks=[
        Subtask(id="st_a", description="the interrupted step", required_tier=1),
    ])
    state.subtasks[0].status = "in_progress"
    SessionStore().save(state)

    ran = []

    async def _fake(**kwargs):
        ran.append(kwargs["goal"])
        return _loop_result("RESULT: recovered")

    with patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        r = await run_session(
            session_id=state.session_id,
            tools=_build_tools_for_mode(Mode.BUSY),
            horizon_required=False,
        )
    assert r.status == "complete"
    assert len(ran) == 1  # the orphaned subtask actually ran, not skipped
    final = SessionStore().load(state.session_id)
    assert final.subtasks[0].status == "done"


# ── rest point ────────────────────────────────────────────────────────────


def test_rest_point_surfaces_exactly_once(tmp_path):
    from sovereign_agent.rest_point import consume_rest_point, write_rest_point

    write_rest_point(session_id="sess_x", goal="g", data_dir=tmp_path)
    first = consume_rest_point(tmp_path)
    assert first["session_id"] == "sess_x"
    assert consume_rest_point(tmp_path) is None


@pytest.mark.asyncio
async def test_rest_while_idle_bookmarks_and_exits():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.rest_point import consume_rest_point

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        exited = []
        app.exit = lambda *a, **k: exited.append(True)
        app._rest_safely()
        assert exited == [True]
    rp = consume_rest_point()
    assert rp is not None and rp["session_id"] == ""


@pytest.mark.asyncio
async def test_rest_during_session_pauses_at_boundary_then_exits():
    """The handshake: /rest sets the interrupts flag (Gate 2 pauses at the
    next boundary); the worker's finally writes the bookmark and exits."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.interrupts import status as interrupts_status
    from sovereign_agent.rest_point import consume_rest_point

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        exited = []
        app.exit = lambda *a, **k: exited.append(True)
        app._session_running = True
        app._rest_safely()
        assert app._resting is True
        assert exited == []  # not yet — waits for the boundary
        # the engine pauses at Gate 2 → the worker's finally runs:
        class _R:  # the shape _finish_rest reads
            session_id = "sess_rest_test"
        app._last_session_result = _R()
        app._session_running = False
        app._finish_rest()
        assert exited == [True]
    rp = consume_rest_point()
    assert rp is not None and rp["session_id"] == "sess_rest_test"
    # the pause flag was cleared — the next session must not auto-pause
    assert interrupts_status().requested is False


@pytest.mark.asyncio
async def test_chat_mode_resume_proposes_never_runs():
    from sovereign_agent.agent_session import SessionStore, new_session
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.modes import Mode

    store = SessionStore()
    s = new_session(goal="held work", mode=Mode.BUSY)
    s.status = "paused"
    store.save(s)
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        ran = []
        app._run_resume_session_worker = lambda sid: ran.append(sid)
        app._resume_work_session("")
        await pilot.pause()
        assert ran == []
        text = "\n".join(getattr(l, "text", str(l)) for l in app._chat_log.lines)
        assert "proposed, waiting" in text


@pytest.mark.asyncio
async def test_session_store_delete_removes_the_session_and_its_scope():  # resume-menu-forget-d
    """Kevin, 2026-07-21: "a way to maybe delete[] selections if I make
    sessions I no longer need." Deleting must remove both the session
    file and any scope contract saved beside it, and must be a harmless
    no-op (not an error) on an id that's already gone."""
    from sovereign_agent.agent_session import SessionStore, new_session
    from sovereign_agent.modes import Mode
    from sovereign_agent.scope import ScopeContract, load_scope, save_scope

    store = SessionStore()
    s = new_session(goal="a session Kevin no longer wants", mode=Mode.BUSY)
    save_scope(s.session_id, ScopeContract(goal="a session Kevin no longer wants"))
    assert store.path_for(s.session_id).exists()
    assert load_scope(s.session_id) is not None

    assert store.delete(s.session_id) is True
    assert not store.path_for(s.session_id).exists()
    assert load_scope(s.session_id) is None

    # already gone — a second delete is a harmless no-op, not an error
    assert store.delete(s.session_id) is False


def test_forget_session_wraps_the_store_delete():
    from sovereign_agent.agent_session import SessionStore, new_session
    from sovereign_agent.modes import Mode
    from sovereign_agent.session_bridge import forget_session

    store = SessionStore()
    s = new_session(goal="another one to forget", mode=Mode.BUSY)
    assert store.path_for(s.session_id).exists()

    assert forget_session(s.session_id) is True
    assert not store.path_for(s.session_id).exists()
