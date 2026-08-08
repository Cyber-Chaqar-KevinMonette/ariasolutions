"""Tests for session-wall-seconds-d.

Kevin, 2026-07-25: "auto only gives me 1 hour" -- even under an armed
3-hour auto lease, every individual /work or /resume session still
self-capped at start_goal_session's blind wall_seconds=3600 default,
because the only call sites (the work/resume workers in app.py) never
overrode it. _armed_wall_seconds() derives the real ceiling from
lease_remaining_seconds() -- the same read the header already trusts.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_falls_back_to_default_when_no_lease_armed():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.lease_remaining_seconds",
                  return_value=0):
            assert app._armed_wall_seconds() == 3600


@pytest.mark.asyncio
async def test_uses_the_armed_leases_remaining_time_when_longer():
    """The actual bug fix: a 3-hour lease must raise the ceiling well
    past the old blind 1-hour default."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.lease_remaining_seconds",
                  return_value=3 * 3600):
            assert app._armed_wall_seconds() == 3 * 3600


@pytest.mark.asyncio
async def test_never_shrinks_below_the_existing_one_hour_floor():
    """A lease with only a few minutes left must not shrink the session
    below the floor that already existed before this fix."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.lease_remaining_seconds",
                  return_value=300):
            assert app._armed_wall_seconds() == 3600


@pytest.mark.asyncio
async def test_degrades_to_default_if_lease_read_raises():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.modes_crown.profiles.lease_remaining_seconds",
                  side_effect=RuntimeError("boom")):
            assert app._armed_wall_seconds() == 3600


@pytest.mark.asyncio
async def test_work_session_worker_passes_the_armed_wall_seconds():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_armed_wall_seconds", return_value=10800), \
             patch("sovereign_agent.session_bridge.start_goal_session") as start:
            start.return_value.status = "complete"
            start.return_value.pause_reason = ""
            start.return_value.completed_subtasks = 1
            start.return_value.total_subtasks = 1
            start.return_value.total_iterations = 1
            start.return_value.total_tokens = 10
            # @work-decorated -- call the undecorated coroutine directly
            # so this awaits the real work instead of returning a Worker.
            await CockpitApp._run_work_session_worker.__wrapped__(app, "test goal")

        assert start.call_args.kwargs.get("wall_seconds") == 10800


def test_per_subtask_budget_is_2700_seconds():
    """45 minutes -- raised from 1800s to give headroom above the
    observed 10-20+ min actual per-subtask time on this hardware."""
    import inspect
    from sovereign_agent import agent_session

    src = inspect.getsource(agent_session)
    assert "max_iterations=25, max_wall_seconds=2700" in src
