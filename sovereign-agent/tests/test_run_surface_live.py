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


# ── token-speed-d (Kevin, 2026-07-21) ───────────────────────────────────────


def test_token_usage_event_tracks_tok_s():
    """"add a token counter to observability so I can always watch the
    token speed and session token total." tok_s is a NEW field alongside
    the existing running-total tokens count."""
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    assert s.tok_s == 0.0
    s.ingest({"flag": "token-usage-d",
             "payload": {"running_total": 500, "tok_s": 42.5}})
    assert s.tokens == 500
    assert s.tok_s == 42.5


def test_render_token_strip_shows_speed_and_session_total():
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    assert "none yet" in s.render_token_strip()

    s.ingest({"flag": "token-usage-d",
             "payload": {"running_total": 1234, "tok_s": 18.3}})
    strip = s.render_token_strip()
    assert "18.3 tok/s" in strip
    assert "1234t" in strip


def test_new_session_resets_tok_s():
    """ingest-d (a fresh session start) must reset tok_s along with the
    other per-session fields, exactly like it already resets tokens."""
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    s.ingest({"flag": "token-usage-d",
             "payload": {"running_total": 999, "tok_s": 50.0}})
    assert s.tok_s == 50.0

    s.ingest({"flag": "ingest-d", "payload": {"goal": "a new goal", "mode": "oneshot"}})
    assert s.tok_s == 0.0
    assert s.tokens == 0


def test_token_usage_never_raises_on_bad_tok_s():
    from sovereign_agent.cockpit.run_surface import RunState

    s = RunState()
    s.ingest({"flag": "token-usage-d",
             "payload": {"running_total": 10, "tok_s": "not-a-number"}})  # must not raise


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
        # text-wrap-d: the live pane wraps long lines (min_width=1) instead of
        # cropping. A flag can wrap even at a hyphen ("something-" / "broke-x"),
        # so compare with ALL whitespace removed — robust to both hyphen and
        # space wrap points.
        flat = "".join(
            "".join(getattr(l, "text", str(l)) for l in lines).split()
        )
        assert "something-broke-x" in flat


@pytest.mark.asyncio
async def test_tokens_metrics_render_in_the_game_window():
    """Kevin, 2026-07-21: "add a token counter to observability so I can
    always watch the token speed and session token total" -- game-window-d
    (2026-07-25) folded the standalone token strip (which never looked
    right) into the new #game-window; the token data path is the same
    _RUN_STATE this always read, just rendered inside the new window."""
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        window = app.query_one("#game-window", Static)
        rendered = str(window.render())
        assert rendered is not None

        from sovereign_agent.cockpit.app import _RUN_STATE
        _RUN_STATE.tokens = 4321
        _RUN_STATE.tok_s = 12.5
        app._refresh_game_window()
        await pilot.pause()
        window = app.query_one("#game-window", Static)
        rendered = str(window.render())
        assert "12.5 tok/s" in rendered
        assert "4321t" in rendered
        _RUN_STATE.tokens = 0  # tidy up shared module-level state
        _RUN_STATE.tok_s = 0.0
