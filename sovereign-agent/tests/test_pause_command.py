"""Tests for graceful-pause-d — /pause: a real, voluntary, resumable pause
for the in-process work session, distinct from /halt (PROTOCOL-ZERO).

Root cause this closes: interrupts.py already shipped the full mechanism
(request/ack/resume flag files, a one-line checkpoint() hook) and
agent_session.run_session's Gate 2 already calls it every iteration and
sets status="paused" correctly -- but nothing in the cockpit ever called
interrupts.request_conversation() to actually trigger it. /pause is that
trigger, not a new mechanism.

pause-clean-stop-d (Kevin, 2026-07-25): "make /pause end the session. So
I don't have to /pause cancel every time... Just pause, work, or resume."
Bare /pause now only requests a pause when something is actually running
(previously it always wrote a request flag, even with nothing running to
ever acknowledge it -- left dangling until manually cleared). And every
session worker's finally now clears the interrupts flags itself
(_clear_session_busy_state), so /pause cancel is never a required
second step.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_bare_pause_requests_conversation_mode_when_something_is_running():
    from sovereign_agent import interrupts
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        assert interrupts.status().requested is False
        app._handle_slash("/pause")
        state = interrupts.status()
        assert state.requested is True
        assert state.note is None


@pytest.mark.asyncio
async def test_bare_pause_with_nothing_running_is_a_clean_noop():
    """The new guard: no dangling request flag when there's nothing to
    ever acknowledge it."""
    from sovereign_agent import interrupts
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = False
        app._session_running = False
        app._handle_slash("/pause")
        assert interrupts.status().requested is False


@pytest.mark.asyncio
async def test_pause_with_a_note_records_it():
    from sovereign_agent import interrupts
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        app._handle_slash("/pause need to look at something else for a bit")
        state = interrupts.status()
        assert state.requested is True
        assert state.note == "need to look at something else for a bit"


def test_clear_session_busy_state_clears_both_state_machines_together():
    """The actual bug: interrupts.status() and _busy/_session_running used
    to only ever get cleared independently. Now one call clears both."""
    from sovereign_agent import interrupts
    from sovereign_agent.cockpit.app import CockpitApp

    interrupts.request_conversation(note="mid-flight")
    try:
        app = CockpitApp.__new__(CockpitApp)
        app._busy = True
        app._session_running = True
        app._set_input_placeholder = lambda *a, **k: None

        app._clear_session_busy_state()

        assert app._busy is False
        assert app._session_running is False
        assert interrupts.status().requested is False
    finally:
        interrupts.clear_conversation_request()


@pytest.mark.asyncio
async def test_pause_status_does_not_itself_request_a_pause():
    from sovereign_agent import interrupts
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._handle_slash("/pause status")
        assert interrupts.status().requested is False


@pytest.mark.asyncio
async def test_pause_cancel_clears_a_pending_request():
    from sovereign_agent import interrupts
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        app._handle_slash("/pause")
        assert interrupts.status().requested is True
        app._handle_slash("/pause cancel")
        assert interrupts.status().requested is False


@pytest.mark.asyncio
async def test_pause_never_touches_protocol_zero():
    """The whole point of building a SEPARATE command from /halt."""
    from sovereign_agent import protocol_zero
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        app._handle_slash("/pause")
        assert protocol_zero.is_armed() is False


def test_requesting_a_pause_is_actually_seen_by_the_real_session_loop_hook(tmp_path, monkeypatch):
    """Not just 'the command calls the right function name' -- proves the
    full, already-existing wiring: request_conversation() now, then the
    exact hook agent_session.run_session calls every iteration
    (interrupts.checkpoint) returns True, matching what Gate 2 checks."""
    from sovereign_agent import interrupts

    assert interrupts.checkpoint(continuation_id="test-session") is False
    interrupts.request_conversation(note="testing the real hook")
    assert interrupts.checkpoint(continuation_id="test-session") is True
    # checkpoint() firing already acknowledged the pause (matches its own
    # documented contract) -- a second call is a no-op, not a re-trigger.
    state = interrupts.status()
    assert state.acknowledged is True


@pytest.mark.asyncio
async def test_pause_reports_failure_instead_of_crashing(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._busy = True
        monkeypatch.setattr(
            "sovereign_agent.interrupts.request_conversation",
            lambda note=None: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        app._handle_slash("/pause")  # must not raise
