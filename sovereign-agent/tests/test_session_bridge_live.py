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
    # goal-modulator-d: start_goal_session now ALWAYS calls the fast
    # model to modulate the goal -- mock it here so this test proves the
    # single-subtask engine shape deterministically, not whatever a live
    # Ollama call happens to produce for this exact goal text.
    with patch("sovereign_agent.agent_session.agent_loop", new=fake), \
         patch("sovereign_agent.goal_modulator.modulate_goal", new=AsyncMock(return_value=[])):
        result = await start_goal_session("do a small kindness")
    assert result.status == "complete"
    assert result.completed_subtasks == result.total_subtasks == 1


@pytest.mark.asyncio
async def test_resume_clears_a_pending_pause_request():  # graceful-pause-fix-d
    """The actual bug Kevin hit repeatedly: '/pause' sets a request flag;
    without this fix, resuming never told the loop to stand down, so
    run_session's own Gate 2 saw the request still active on the very
    first iteration and immediately re-paused -- "I cannot resume any
    task unless I /pause cancel first."

    run_session itself is mocked here (it's the real engine loop), so the
    thing to assert isn't `status().requested` -- that only flips to False
    once the real (unmocked) run_session's consume_resume() runs. The
    fix's own effect, reachable without the real loop, is that the
    loop-facing hook (check_conversation_request / checkpoint) stops
    signalling "pause" the instant request_resume() has been called --
    proven directly in test_resume_fix_actually_prevents_the_instant_repause.
    Here we prove resume_goal_session is the thing that actually calls it.
    """
    from sovereign_agent import interrupts
    from sovereign_agent.agent_session import SessionResult
    from sovereign_agent.session_bridge import resume_goal_session

    interrupts.request_conversation(note="operator wants to talk")
    assert interrupts.status().requested is True
    assert interrupts.status().resume_pending is False

    fake = AsyncMock(return_value=SessionResult(
        session_id="s1", status="complete", completed_subtasks=1,
        total_subtasks=1, total_iterations=1, total_tokens=1,
        elapsed_seconds=0.1,
    ))
    with patch("sovereign_agent.agent_session.run_session", new=fake), \
         patch("sovereign_agent.session_bridge._lease_check"), \
         patch("sovereign_agent.session_bridge._crown_gate"), \
         patch("sovereign_agent.agent_session.SessionStore") as mock_store:
        mock_state = mock_store.return_value.load.return_value
        mock_state.mode = "oneshot"
        await resume_goal_session("s1")

    # request_resume() was actually called: the resume flag is now set,
    # and the loop-facing hook no longer signals "pause" -- the exact
    # condition that used to make the very next Gate 2 check re-pause.
    assert interrupts.status().resume_pending is True
    assert interrupts.check_conversation_request() is False


@pytest.mark.asyncio
async def test_resuming_with_no_pending_pause_is_a_harmless_noop():
    from sovereign_agent import interrupts
    from sovereign_agent.agent_session import SessionResult
    from sovereign_agent.session_bridge import resume_goal_session

    assert interrupts.status().requested is False

    fake = AsyncMock(return_value=SessionResult(
        session_id="s1", status="complete", completed_subtasks=1,
        total_subtasks=1, total_iterations=1, total_tokens=1,
        elapsed_seconds=0.1,
    ))
    with patch("sovereign_agent.agent_session.run_session", new=fake), \
         patch("sovereign_agent.session_bridge._lease_check"), \
         patch("sovereign_agent.session_bridge._crown_gate"), \
         patch("sovereign_agent.agent_session.SessionStore") as mock_store:
        mock_state = mock_store.return_value.load.return_value
        mock_state.mode = "oneshot"
        await resume_goal_session("s1")  # must not raise

    assert interrupts.status().requested is False
    assert interrupts.check_conversation_request() is False


def test_resume_fix_actually_prevents_the_instant_repause():
    """Proves the real-world effect directly against interrupts.checkpoint()
    -- the exact call run_session's Gate 2 makes every iteration -- rather
    than just asserting request_resume() was called."""
    from sovereign_agent import interrupts

    interrupts.request_conversation(note="operator wants to talk")
    interrupts.checkpoint(continuation_id="s1")  # simulates the ORIGINAL pause firing
    assert interrupts.status().is_paused is True

    interrupts.request_resume()  # the fix's actual effect
    # Gate 2's exact call, right after "resuming" -- must NOT fire again.
    assert interrupts.checkpoint(continuation_id="s1") is False


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
               new=AsyncMock(side_effect=_capture_run_session)), \
         patch("sovereign_agent.goal_modulator.modulate_goal", new=AsyncMock(return_value=[])):
        await sb.start_goal_session("g", wall_seconds=3600, safety_margin_seconds=360)
    b: RunBudget = captured["budget"]
    assert b.max_wall_seconds == 3600
    assert b.safety_margin_seconds == 360


@pytest.mark.asyncio
async def test_min_minutes_drives_modulation_target_independent_of_ceiling():
    """work-deadline-args-d: min_minutes sizes the subtask decomposition
    (target_minutes) while wall_seconds stays the separate hard ceiling —
    two independent knobs, not one."""
    import sovereign_agent.session_bridge as sb

    async def _capture_run_session(**kwargs):
        from sovereign_agent.agent_session import SessionResult
        return SessionResult(session_id="x", status="complete",
                             completed_subtasks=1, total_subtasks=1,
                             total_iterations=1, total_tokens=1,
                             elapsed_seconds=0.1)

    captured_target = {}

    async def _capture_modulate(goal, *, target_minutes=None, **kw):
        captured_target["target_minutes"] = target_minutes
        return []

    with patch("sovereign_agent.agent_session.run_session",
              new=AsyncMock(side_effect=_capture_run_session)), \
         patch("sovereign_agent.goal_modulator.modulate_goal",
              new=AsyncMock(side_effect=_capture_modulate)):
        await sb.start_goal_session("g", wall_seconds=7200, min_minutes=45)

    assert captured_target["target_minutes"] == 45  # not 7200 // 60 == 120


@pytest.mark.asyncio
async def test_min_minutes_never_exceeds_the_hard_ceiling():
    """A min longer than the requested max would be contradictory --
    the ceiling still wins (raised, never silently shrunk)."""
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
              new=AsyncMock(side_effect=_capture_run_session)), \
         patch("sovereign_agent.goal_modulator.modulate_goal", new=AsyncMock(return_value=[])):
        await sb.start_goal_session("g", wall_seconds=1800, min_minutes=90)  # 90m > 30m ceiling

    b: RunBudget = captured["budget"]
    assert b.max_wall_seconds == 90 * 60  # raised to cover the min, not shrunk


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
        app._run_work_session_worker = lambda goal, mn=None, mx=None: ran.append(goal)
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
        # text-wrap-d: chat pane wraps long lines (min_width=1); normalize
        # whitespace so the (now wrapped) confirmation phrase still matches.
        text = " ".join(
            " ".join(getattr(l, "text", str(l)) for l in app._chat_log.lines).split()
        )
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
               new=AsyncMock(side_effect=_capture)), \
         patch("sovereign_agent.goal_modulator.modulate_goal", new=AsyncMock(return_value=[])):
        await sb.start_goal_session("g", wall_seconds=180)
    from sovereign_agent.modes import effective_wall_limit

    b = captured["budget"]
    assert effective_wall_limit(b) > 0
    assert b.safety_margin_seconds <= 60
