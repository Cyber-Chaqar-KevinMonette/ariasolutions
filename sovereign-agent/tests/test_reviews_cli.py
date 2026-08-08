"""Tests for sov-reviews-cli-d.

Found 2026-07-25 while verifying Phase 5's Discord task-report ask:
session_bridge.py's Discord work-update message has said "full trail:
`sov reviews show <sid>`" since work-updates-d (2026-07-18) -- that
command never existed anywhere in cli.py. Every finished session's
Discord message pointed Kevin at a dead command. `sov reviews list` /
`sov reviews show <id>` close the gap using review_journal.py exactly
as the cockpit's own /review and /reviews chat commands already do.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sovereign_agent.cli import ExitCode, app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_a_review(data_dir: Path, session_id: str = "sess-abc123") -> None:
    from sovereign_agent.review_journal import build_review

    state = {
        "session_id": session_id, "goal": "test the reviews CLI",
        "mode": "busy", "status": "complete", "created_at": "t0", "updated_at": "t1",
        "subtasks": [], "pause_reason": None, "last_error": None,
    }
    build_review(state, data_dir=data_dir)


def test_reviews_list_when_empty_names_where_they_will_land(runner, tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data),
                                 "reviews", "list"])
    assert result.exit_code == ExitCode.OK, result.stdout
    assert "no reviews yet" in result.stdout
    assert str(data) in result.stdout


def test_reviews_list_shows_a_real_session(runner, tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    _write_a_review(data)
    result = runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data),
                                 "reviews", "list"])
    assert result.exit_code == ExitCode.OK, result.stdout
    assert "sess-abc123" in result.stdout


def test_reviews_show_prints_the_readme_and_path(runner, tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    _write_a_review(data)
    result = runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data),
                                 "reviews", "show", "sess-abc123"])
    assert result.exit_code == ExitCode.OK, result.stdout
    assert "test the reviews CLI" in result.stdout
    assert "full record:" in result.stdout


def test_reviews_show_accepts_a_short_suffix(runner, tmp_path):
    """Matches the Discord message's own truncated sid[:12] format."""
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    _write_a_review(data, session_id="a-very-long-session-id-abc123")
    result = runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data),
                                 "reviews", "show", "abc123"])
    assert result.exit_code == ExitCode.OK, result.stdout
    assert "test the reviews CLI" in result.stdout


def test_reviews_show_unknown_id_exits_nonzero_with_a_clear_message(runner, tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    result = runner.invoke(app, ["--config-dir", str(cfg), "--data-dir", str(data),
                                 "reviews", "show", "ghost-session"])
    assert result.exit_code != ExitCode.OK
    assert "no review found" in result.stdout
    assert "sov reviews list" in result.stdout
