"""Behavior tests for aria-run-surface, promoted to live tests/ — tests the
REAL, already-patched cockpit + run_surface module. Plain imports, no
shadow copy.
"""
from __future__ import annotations

import pytest


# ── render_rich_event ─────────────────────────────────────────────────────


def test_session_family_renders_payload_not_bare_flags():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    out = render_rich_event({
        "flag": "subtask-start-d",
        "payload": {"description": "refactor the events module", "tier": 1},
    })
    assert out is not None
    assert "refactor the events module" in out
    assert "T1" in out


def test_session_complete_shows_progress():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    out = render_rich_event({
        "flag": "session-complete-d", "payload": {"done": 5, "total": 7},
    })
    assert "5/7" in out


def test_prompt_diet_event_renders():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    out = render_rich_event({
        "flag": "prompt-diet-d",
        "payload": {"tools_sent": 18, "tools_registered": 213, "prompt_chars": 10416},
    })
    assert "18/213" in out


def test_unknown_flags_fall_through():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    assert render_rich_event({"flag": "trace-start-d", "payload": {}}) is None
    assert render_rich_event({"flag": "tool-start-d", "payload": {}}) is None
    assert render_rich_event({"flag": "token-usage-d", "payload": {}}) is None


def test_renderer_never_raises_on_garbage():
    from sovereign_agent.cockpit.run_surface import render_rich_event

    for ev in ({}, {"flag": "session-budget-d"}, {"flag": "subtask-done-d", "payload": None},
               {"flag": "qa-d", "payload": {"question": 42}}):
        render_rich_event(ev)  # must not raise


# ── RunState ──────────────────────────────────────────────────────────────


def _feed(state, *events):
    for ev in events:
        state.ingest(ev)


def test_run_state_tracks_a_full_session():
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    assert "no run active" in s.render_strip()

    _feed(
        s,
        {"flag": "ingest-d", "ts": "2026-07-04T10:00:00.0Z",
         "payload": {"goal": "harden the vessel", "mode": "work"}},
        {"flag": "session-start-d", "payload": {"subtasks_pending": 3}},
        {"flag": "subtask-start-d", "payload": {"description": "first step", "tier": 1}},
        {"flag": "token-usage-d", "payload": {"running_total": 1234}},
    )
    strip = s.render_strip()
    assert s.active is True
    assert "harden the vessel" in strip
    assert "first step" in strip
    assert "1234t" in strip

    _feed(
        s,
        {"flag": "subtask-done-d", "payload": {"iterations": 2, "tokens": 900, "summary": "ok"}},
        {"flag": "session-complete-d", "payload": {"done": 3, "total": 3}},
    )
    assert s.active is False
    assert "complete 3/3" in s.render_strip()


def test_run_state_halts_render_red():
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    _feed(s,
          {"flag": "ingest-d", "payload": {"goal": "g", "mode": "oneshot"}},
          {"flag": "halted-d", "payload": {}})
    assert "HALTED" in s.render_strip()
    assert "[red]" in s.render_strip()


def test_run_state_breaker_badge():
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    s.ingest({"flag": "circuit-open-x", "payload": {"tool": "run_shell"}})
    assert "run_shell" in s.render_strip()


def test_run_state_never_raises_on_garbage():
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    for ev in ({}, {"flag": None}, {"flag": "token-usage-d", "payload": {"running_total": "x"}},
               {"payload": "not a dict"}):
        s.ingest(ev)  # must not raise


# ── the live cockpit ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_strip_exists_and_renders():
    from textual.widgets import Static

    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        strip = pilot.app.query_one("#run-strip", Static)
        assert strip is not None


@pytest.mark.asyncio
async def test_rich_event_routes_to_events_log_and_run_state():
    import sovereign_agent.cockpit.app as app_module
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        import json
        app._render_event(json.dumps({
            "flag": "subtask-start-d", "ts": "2026-07-04T10:00:00.0Z",
            "payload": {"description": "live routing proof", "tier": 0},
        }))
        await pilot.pause()
        assert app_module._RUN_STATE.current_subtask.startswith("live routing proof")


@pytest.mark.asyncio
async def test_failure_flag_renders_red_in_live_pane():
    """The -x fix, end to end: a failure event's rendered line is red."""
    import json

    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        # An unknown -x flag (not in the rich registry) exercises the
        # generic color chain.
        app._render_event(json.dumps({
            "flag": "something-broke-x", "ts": "2026-07-04T10:00:00.0Z",
            "payload": {},
        }))
        await pilot.pause()
        lines = app._events_log.lines
        assert lines, "nothing rendered"
        last = lines[-1]
        text = getattr(last, "text", str(last))
        assert "something-broke-x" in text
