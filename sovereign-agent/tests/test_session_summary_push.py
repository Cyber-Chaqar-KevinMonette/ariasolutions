"""Tests for session-summary-push-d.

Kevin, 2026-07-25: "at the end of every session... the system show
automatically begin summary docs for you and I to review... present
where the docs are located... open the file location for us." The
review directory (review_journal.build_review()) was already written
by session_bridge for every session, complete or paused -- nothing ever
told Kevin where it landed. _announce_review_ready() looks it up and
prints the path; /open-reports opens the folder on request.

Also covers a real bug caught while building this: _run_resume_session_worker's
finally block still had the OLD inline _busy/_session_running clearing
(pre pause-clean-stop-d), missing the interrupts-flag clear
_clear_session_busy_state() provides -- so a resumed-then-paused session
could still show stuck "working" text, the exact bug already fixed for
the work-session path but not this one.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_announce_review_ready_prints_the_path_when_it_exists(tmp_path):
    from sovereign_agent.cockpit import CockpitApp

    review_dir = tmp_path / "reviews" / "sess-123"
    review_dir.mkdir(parents=True)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.review_journal.reviews_root",
                  return_value=tmp_path / "reviews"), \
             patch.object(app, "_write_meta") as write_meta:
            app._announce_review_ready("sess-123")

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "review written" in messages
        assert "sess-123" in messages
        assert "/open-reports" in messages


@pytest.mark.asyncio
async def test_announce_review_ready_says_nothing_when_no_review_exists():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_write_meta") as write_meta:
            app._announce_review_ready("a-session-that-never-wrote-a-review")

        write_meta.assert_not_called()


@pytest.mark.asyncio
async def test_open_reports_command_launches_xdg_open(tmp_path):
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.review_journal.reviews_root",
                  return_value=tmp_path / "reviews"), \
             patch("subprocess.Popen") as popen, \
             patch.object(app, "_write_meta") as write_meta:
            app._open_reports_folder()

        # An unrelated periodic daemon-status check in the cockpit also
        # shells out via subprocess.Popen (e.g. systemctl) and can fire
        # during this window -- match the specific xdg-open call rather
        # than asserting this mock saw exactly one call of any kind.
        xdg_calls = [c for c in popen.call_args_list
                    if c.args and c.args[0] and c.args[0][0] == "xdg-open"]
        assert len(xdg_calls) == 1
        args = xdg_calls[0].args[0]
        assert str(tmp_path / "reviews") in args[1]
        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "opening" in messages


@pytest.mark.asyncio
async def test_open_reports_degrades_gracefully_without_xdg_open(tmp_path):
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.review_journal.reviews_root",
                  return_value=tmp_path / "reviews"), \
             patch("subprocess.Popen", side_effect=FileNotFoundError), \
             patch.object(app, "_write_meta") as write_meta:
            app._open_reports_folder()  # must not raise

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "xdg-open not available" in messages


@pytest.mark.asyncio
async def test_open_reports_slash_command_wired():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_open_reports_folder") as handler:
            app._handle_slash("/open-reports")
        handler.assert_called_once()


@pytest.mark.asyncio
async def test_resume_worker_finally_clears_busy_state_via_shared_helper():
    """Regression: this block used to inline the old clearing logic,
    missing the interrupts-flag clear pause-clean-stop-d added for the
    work-session path -- a resumed-then-paused session could still show
    stuck 'working' text."""
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_clear_session_busy_state") as clear_state, \
             patch("sovereign_agent.session_bridge.resume_goal_session",
                  side_effect=RuntimeError("boom")):
            await CockpitApp._run_resume_session_worker.__wrapped__(app, "sid-1")

        clear_state.assert_called_once()


@pytest.mark.asyncio
async def test_work_session_worker_announces_review_after_success():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        fake_result = MagicMock(
            status="complete", pause_reason="", session_id="sess-xyz",
            completed_subtasks=1, total_subtasks=1, total_iterations=1, total_tokens=10,
        )
        with patch("sovereign_agent.session_bridge.start_goal_session",
                  return_value=fake_result), \
             patch.object(app, "_announce_review_ready") as announce:
            await CockpitApp._run_work_session_worker.__wrapped__(app, "a goal")

        announce.assert_called_once_with("sess-xyz")
