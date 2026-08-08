"""Tests for movie-studio-d — the visible movie-dev XP/level ledger."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_dev_xp import (
    XP_MILESTONE,
    XP_PITCH_ACCEPTED,
    XP_SHIPPED,
    XP_STORYBOARD_GENERATED,
    XP_TREATMENT_DRAFTED,
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
        award("", "treatment_drafted", data_dir=tmp_path)


def test_award_uses_named_constant_never_arbitrary(tmp_path):
    ev = award("proj-a", "treatment_drafted", note="wrote the treatment", data_dir=tmp_path)
    assert ev.xp == XP_TREATMENT_DRAFTED
    ev2 = award("proj-a", "milestone", note="first storyboard sequence locked", data_dir=tmp_path)
    assert ev2.xp == XP_MILESTONE


def test_load_events_round_trips(tmp_path):
    award("proj-a", "treatment_drafted", data_dir=tmp_path)
    award("proj-a", "storyboard_generated", note="opening shot", data_dir=tmp_path)
    events = load_events(tmp_path)
    assert len(events) == 2
    assert events[0].event_type == "treatment_drafted"
    assert events[1].xp == XP_STORYBOARD_GENERATED


def test_load_events_skips_torn_lines(tmp_path):
    from sovereign_agent.movie_dev_xp import xp_ledger_path
    award("proj-a", "treatment_drafted", data_dir=tmp_path)
    path = xp_ledger_path(tmp_path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    events = load_events(tmp_path)
    assert len(events) == 1


def test_total_xp_grand_and_per_project(tmp_path):
    award("proj-a", "treatment_drafted", data_dir=tmp_path)   # 15
    award("proj-a", "milestone", data_dir=tmp_path)            # 50
    award("proj-b", "shipped", data_dir=tmp_path)              # 250
    assert total_xp(data_dir=tmp_path) == 15 + 50 + 250
    assert total_xp("proj-a", data_dir=tmp_path) == 65
    assert total_xp("proj-b", data_dir=tmp_path) == 250


def test_pitch_accepted_rewards_a_picked_pitch(tmp_path):
    ev = award("proj-a", "pitch_accepted", note="picked the AI-futures pitch", data_dir=tmp_path)
    assert ev.xp == XP_PITCH_ACCEPTED


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
        award("proj-a", "treatment_drafted", note=f"draft {i}", data_dir=tmp_path)
    recent = recent_events(3, data_dir=tmp_path)
    assert len(recent) == 3
    assert recent[0].note == "draft 4"  # most recent first


def test_recent_events_filters_by_project(tmp_path):
    award("proj-a", "treatment_drafted", data_dir=tmp_path)
    award("proj-b", "treatment_drafted", data_dir=tmp_path)
    recent = recent_events(10, project_slug="proj-b", data_dir=tmp_path)
    assert len(recent) == 1
    assert recent[0].project_slug == "proj-b"
