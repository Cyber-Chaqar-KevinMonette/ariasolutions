"""Tests for game-studio-d — the visible game-dev XP/level ledger."""
from __future__ import annotations

import pytest

from sovereign_agent.game_dev_xp import (
    XP_LESSON_LOGGED,
    XP_MILESTONE,
    XP_SESSION_FOCUSED,
    XP_SHIPPED,
    XP_TASK_COMPLETED,
    award,
    level_for_xp,
    load_events,
    progress_to_next,
    recent_events,
    total_xp,
)


def test_award_unknown_event_type_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown event_type"):
        award("proj", "made_up_event", data_dir=tmp_path)


def test_award_requires_project_slug(tmp_path):
    with pytest.raises(ValueError, match="project_slug"):
        award("", "task_completed", data_dir=tmp_path)


def test_award_uses_named_constant_never_arbitrary(tmp_path):
    ev = award("proj-a", "task_completed", note="fixed the jump bug", data_dir=tmp_path)
    assert ev.xp == XP_TASK_COMPLETED
    ev2 = award("proj-a", "milestone", note="first playable level", data_dir=tmp_path)
    assert ev2.xp == XP_MILESTONE


def test_load_events_round_trips(tmp_path):
    award("proj-a", "task_completed", data_dir=tmp_path)
    award("proj-a", "lesson_logged", note="tilemap collision gotcha", data_dir=tmp_path)
    events = load_events(tmp_path)
    assert len(events) == 2
    assert events[0].event_type == "task_completed"
    assert events[1].xp == XP_LESSON_LOGGED


def test_load_events_skips_torn_lines(tmp_path):
    from sovereign_agent.game_dev_xp import xp_ledger_path
    award("proj-a", "task_completed", data_dir=tmp_path)
    path = xp_ledger_path(tmp_path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    events = load_events(tmp_path)
    assert len(events) == 1


def test_total_xp_grand_and_per_project(tmp_path):
    award("proj-a", "task_completed", data_dir=tmp_path)     # 10
    award("proj-a", "milestone", data_dir=tmp_path)           # 50
    award("proj-b", "shipped", data_dir=tmp_path)              # 250
    assert total_xp(data_dir=tmp_path) == 10 + 50 + 250
    assert total_xp("proj-a", data_dir=tmp_path) == 60
    assert total_xp("proj-b", data_dir=tmp_path) == 250


def test_session_focused_bonus_rewards_discipline(tmp_path):
    ev = award("proj-a", "session_focused", note="3h block, stayed on proj-a", data_dir=tmp_path)
    assert ev.xp == XP_SESSION_FOCUSED


def test_level_for_xp_is_linear():
    assert level_for_xp(0) == 1
    assert level_for_xp(249) == 1
    assert level_for_xp(250) == 2
    assert level_for_xp(999) == 4


def test_progress_to_next():
    within, per_level = progress_to_next(260)
    assert within == 10
    assert per_level == 250


def test_recent_events_most_recent_first_and_bounded(tmp_path):
    for i in range(5):
        award("proj-a", "task_completed", note=f"task {i}", data_dir=tmp_path)
    recent = recent_events(3, data_dir=tmp_path)
    assert len(recent) == 3
    assert recent[0].note == "task 4"  # most recent first


def test_recent_events_filters_by_project(tmp_path):
    award("proj-a", "task_completed", data_dir=tmp_path)
    award("proj-b", "task_completed", data_dir=tmp_path)
    recent = recent_events(10, project_slug="proj-b", data_dir=tmp_path)
    assert len(recent) == 1
    assert recent[0].project_slug == "proj-b"
