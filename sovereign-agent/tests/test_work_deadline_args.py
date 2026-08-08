"""Tests for work-deadline-args-d.

Kevin, 2026-07-25: "/work <goal> <min timeframe/deadline to complete
task> <maximum deadline to complete task>". Trailing duration-shaped
tokens ('45m', '2h', '2h30m') are parsed off the raw /work argument
string -- one token is the max (today's single-ceiling meaning,
unchanged), two are (min, max). Anything not duration-shaped stays part
of the goal text.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sovereign_agent.goal_modulator import parse_work_args


def test_no_trailing_duration_leaves_the_whole_string_as_goal():
    goal, mn, mx = parse_work_args("refactor the parser")
    assert goal == "refactor the parser"
    assert mn is None
    assert mx is None


def test_single_trailing_token_is_the_max():
    goal, mn, mx = parse_work_args("refactor the parser 2h")
    assert goal == "refactor the parser"
    assert mn is None
    assert mx == 120


def test_two_trailing_tokens_are_min_then_max():
    goal, mn, mx = parse_work_args("refactor the parser 45m 2h")
    assert goal == "refactor the parser"
    assert mn == 45
    assert mx == 120


def test_combined_hours_and_minutes_token():
    goal, mn, mx = parse_work_args("deep research 1h 2h30m")
    assert goal == "deep research"
    assert mn == 60
    assert mx == 150


def test_a_goal_ending_in_an_ordinary_word_is_not_misparsed():
    goal, mn, mx = parse_work_args("clean up the room")
    assert goal == "clean up the room"
    assert mn is None
    assert mx is None


def test_empty_input():
    goal, mn, mx = parse_work_args("")
    assert goal == ""
    assert mn is None
    assert mx is None


def test_goal_that_is_only_a_duration_token_is_still_readable_as_a_goal():
    """Edge case: a goal with NO other words and a trailing duration --
    both duration slots get consumed, leaving an empty goal (caller's
    usual empty-goal handling applies)."""
    goal, mn, mx = parse_work_args("2h")
    assert mx == 120


# ── cockpit wiring ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_work_session_passes_parsed_deadlines_through():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit_modes import CockpitMode, set_mode

    set_mode(CockpitMode.WORK)
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        calls = []
        app._run_work_session_worker = lambda goal, mn=None, mx=None: calls.append((goal, mn, mx))
        app._start_work_session("harden the review docs 45m 2h")
        await pilot.pause()

        assert calls == [("harden the review docs", 45, 120)]


@pytest.mark.asyncio
async def test_work_session_worker_uses_max_minutes_as_wall_seconds():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import MagicMock

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_result = MagicMock(
            status="complete", pause_reason="", session_id="s1",
            completed_subtasks=1, total_subtasks=1, total_iterations=1, total_tokens=1,
        )
        with patch("sovereign_agent.session_bridge.start_goal_session",
                  return_value=fake_result) as start, \
             patch.object(app, "_announce_review_ready"):
            await CockpitApp._run_work_session_worker.__wrapped__(
                app, "a goal", 45, 120,
            )

        assert start.call_args.kwargs["wall_seconds"] == 120 * 60
        assert start.call_args.kwargs["min_minutes"] == 45


@pytest.mark.asyncio
async def test_work_session_worker_falls_back_to_armed_lease_when_no_max_given():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import MagicMock

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_result = MagicMock(
            status="complete", pause_reason="", session_id="s1",
            completed_subtasks=1, total_subtasks=1, total_iterations=1, total_tokens=1,
        )
        with patch.object(app, "_armed_wall_seconds", return_value=9999), \
             patch("sovereign_agent.session_bridge.start_goal_session",
                  return_value=fake_result) as start, \
             patch.object(app, "_announce_review_ready"):
            await CockpitApp._run_work_session_worker.__wrapped__(app, "a goal")

        assert start.call_args.kwargs["wall_seconds"] == 9999
        assert start.call_args.kwargs["min_minutes"] is None
