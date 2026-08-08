"""Tests for resume-gating-clarity-d.

Kevin, 2026-07-25: "It says they are resumable but when I click on it
nothing happens... I selected the session I wanted... but it still did
not resume." Root cause: two independent gates could block a resume --
chat/work mode (already checked before starting) and the crown profile's
own work-allowed check (only ever raised deep inside the worker, AFTER
the cockpit had already said "resuming"). resume_blocked_reason() runs
the crown check as a dry run so the real reason is known up front.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_resume_blocked_reason_is_none_when_crown_never_armed():
    from sovereign_agent.session_bridge import resume_blocked_reason

    with patch("sovereign_agent.modes_crown.profiles.crown_armed", return_value=False):
        assert resume_blocked_reason("some-session") is None


def test_resume_blocked_reason_names_the_real_cause_when_profile_disallows_work():
    from sovereign_agent.session_bridge import resume_blocked_reason
    from sovereign_agent.modes_crown.profiles import PROFILES

    with patch("sovereign_agent.modes_crown.profiles.crown_armed", return_value=True), \
         patch("sovereign_agent.modes_crown.profiles.current_profile",
               return_value=PROFILES["companion"]):
        reason = resume_blocked_reason("some-session")

    assert reason is not None
    assert "companion" in reason
    assert "modes" in reason.lower() or "F2" in reason


def test_resume_blocked_reason_none_when_profile_allows_work():
    from sovereign_agent.session_bridge import resume_blocked_reason
    from sovereign_agent.modes_crown.profiles import PROFILES

    with patch("sovereign_agent.modes_crown.profiles.crown_armed", return_value=True), \
         patch("sovereign_agent.modes_crown.profiles.current_profile",
               return_value=PROFILES["work"]), \
         patch("sovereign_agent.modes_crown.stances.cooling_down", return_value=False):
        assert resume_blocked_reason("some-session") is None


@pytest.mark.asyncio
async def test_resume_work_session_surfaces_the_crown_reason_immediately():
    """The actual UX bug: this must fire BEFORE the worker starts, not
    get discovered later as a generic 'resume error:' line."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_session = type("S", (), {
            "session_id": "abc123", "status": "paused", "goal": "test goal",
            "subtasks": [],
        })()
        with patch("sovereign_agent.session_bridge.resumable_sessions",
                  return_value=[fake_session]), \
             patch("sovereign_agent.cockpit_modes.autonomous_loops_allowed", return_value=True), \
             patch("sovereign_agent.session_bridge.resume_blocked_reason",
                  return_value="mode 'companion' does not run work sessions"), \
             patch.object(app, "_write_meta") as write_meta, \
             patch.object(app, "_run_resume_session_worker") as worker:
            app._resume_work_session("abc123")

        worker.assert_not_called()
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "companion" in messages
        assert "can't resume yet" in messages
