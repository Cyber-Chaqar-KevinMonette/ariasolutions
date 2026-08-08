"""Tests for recap-command-d.

Kevin, 2026-07-25: "Maybe we can add recap last work session(s) events."
compose_recap() reuses each session's already-written plan.json (written
by review_journal.build_review() at every session end, Phase 3's own
session-summary-push-d) rather than re-deriving anything new.
"""
from __future__ import annotations

import json

import pytest


def _write_review(data_dir, session_id, *, goal, status="complete",
                  done=2, total=2, pause_reason=None, last_error=None):
    from sovereign_agent.review_journal import build_review

    state = {
        "session_id": session_id, "goal": goal, "mode": "busy", "status": status,
        "created_at": "t0", "updated_at": "t1", "pause_reason": pause_reason,
        "last_error": last_error,
        "subtasks": [
            {"id": f"st{i}", "description": f"step {i}", "status": "done",
             "required_tier": 1, "result_summary": "", "trace_id": None, "error": None}
            for i in range(done)
        ] + [
            {"id": f"st{i}", "description": f"step {i}", "status": "pending",
             "required_tier": 1, "result_summary": "", "trace_id": None, "error": None}
            for i in range(done, total)
        ],
    }
    build_review(state, data_dir=data_dir)


def test_recap_with_no_sessions_says_so_plainly(tmp_path):
    from sovereign_agent.review_journal import compose_recap

    text = compose_recap(tmp_path, n=3)
    assert "No sessions recorded" in text


def test_recap_shows_goal_status_and_progress(tmp_path):
    from sovereign_agent.review_journal import compose_recap

    _write_review(tmp_path, "sess-1", goal="fix the atom count bug")
    text = compose_recap(tmp_path, n=3)
    assert "fix the atom count bug" in text
    assert "2/2 subtasks" in text
    assert "sess-1" in text


def test_recap_surfaces_pause_reason_and_error(tmp_path):
    from sovereign_agent.review_journal import compose_recap

    _write_review(tmp_path, "sess-2", goal="a paused goal", status="paused",
                  done=1, total=3, pause_reason="budget exceeded",
                  last_error="timeout on tool X")
    text = compose_recap(tmp_path, n=3)
    assert "a paused goal" in text
    assert "budget exceeded" in text
    assert "timeout on tool X" in text


def test_recap_respects_n_limit(tmp_path):
    from sovereign_agent.review_journal import compose_recap
    import time

    for i in range(5):
        _write_review(tmp_path, f"sess-{i}", goal=f"goal {i}")
        time.sleep(0.01)  # distinct mtimes for newest-first ordering

    text = compose_recap(tmp_path, n=2)
    assert "last 2 session" in text


@pytest.mark.asyncio
async def test_slash_recap_command_wired():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_show_recap") as handler:
            app._handle_slash("/recap 5")
        handler.assert_called_once_with("5")


@pytest.mark.asyncio
async def test_recap_rejects_non_numeric_arg_without_crashing():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._show_recap("banana")  # must not raise
