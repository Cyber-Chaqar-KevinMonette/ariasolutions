"""Tests for aria_xp — the general task-scoring ledger.

Kevin, 2026-07-25: "For each task in the live window. The AI can score
points. Good and successful task plus 10 points. If the AI does
something bad or makes a mistake minus 5 points. If a mistake is made. A
series of events should follow. Note the mistake. Summarize the
situation. How to avoid it in the future. Lock it in memory. Then plan
the solution."
"""
from __future__ import annotations

import pytest

from sovereign_agent.aria_xp import (
    XP_ATOM_WRITTEN,
    XP_MISTAKE,
    XP_PATTERN_RECALLED,
    XP_PATTERN_RECOGNIZED,
    XP_TASK_SUCCESS,
    award,
    level_for_xp,
    load_events,
    progress_to_next,
    record_mistake,
    recent_events,
    total_xp,
)


def test_award_unknown_event_type_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown event_type"):
        award("made_up_event", data_dir=tmp_path)


def test_award_uses_named_constants_never_arbitrary(tmp_path):
    ev = award("task_success", note="fixed the atom-count bug", data_dir=tmp_path)
    assert ev.xp == XP_TASK_SUCCESS == 10
    ev2 = award("pattern_recognized", data_dir=tmp_path)
    assert ev2.xp == XP_PATTERN_RECOGNIZED
    ev3 = award("pattern_recalled", data_dir=tmp_path)
    assert ev3.xp == XP_PATTERN_RECALLED
    ev4 = award("atom_written", data_dir=tmp_path)
    assert ev4.xp == XP_ATOM_WRITTEN


def test_no_project_slug_required_unlike_game_dev_xp(tmp_path):
    """The real distinction from game_dev_xp.py -- most of Aria's work
    isn't tied to a game project."""
    ev = award("task_success", note="general work", data_dir=tmp_path)
    assert ev.event_type == "task_success"


def test_load_events_round_trips(tmp_path):
    award("task_success", data_dir=tmp_path)
    award("memory_written", note="a real fact", data_dir=tmp_path)
    events = load_events(tmp_path)
    assert len(events) == 2
    assert events[0].event_type == "task_success"


def test_total_xp_sums_across_positive_and_negative(tmp_path):
    award("task_success", data_dir=tmp_path)  # +10
    award("task_success", data_dir=tmp_path)  # +10
    award("mistake", note="a real mistake", data_dir=tmp_path)  # -5
    assert total_xp(tmp_path) == 15


def test_level_never_drops_below_1_even_with_negative_total():
    assert level_for_xp(-100) == 1
    assert level_for_xp(0) == 1
    assert level_for_xp(250) == 2


def test_progress_to_next_clamps_negative_totals_to_zero():
    within, needed = progress_to_next(-30)
    assert within == 0
    assert needed == 250


def test_recent_events_most_recent_first(tmp_path):
    award("task_success", note="first", data_dir=tmp_path)
    award("task_success", note="second", data_dir=tmp_path)
    events = recent_events(n=5, data_dir=tmp_path)
    assert events[0].note == "second"
    assert events[1].note == "first"


# ── record_mistake() — the real sequence, not just a point deduction ────


def test_record_mistake_deducts_the_named_constant(tmp_path):
    ev = record_mistake(
        what_happened="wrote to the wrong atom store",
        how_to_avoid="always check which store a tool actually writes to",
        data_dir=tmp_path,
    )
    assert ev.xp == XP_MISTAKE == -5
    assert ev.event_type == "mistake"
    assert ev.case_id  # linked to a real diagnosis.py case


def test_record_mistake_opens_a_full_conflict_diagnosis_resolution_case(tmp_path):
    from sovereign_agent.diagnosis import ConflictCatalog

    ev = record_mistake(
        what_happened="assumed a tool existed that didn't",
        how_to_avoid="verify tool names against the live registry first",
        summary="hallucinated a tool call",
        data_dir=tmp_path,
    )

    catalog = ConflictCatalog(tmp_path / "diagnoses")
    conflict = catalog.get_conflict(ev.case_id)
    diagnosis = catalog.get_diagnosis(ev.case_id)
    resolution = catalog.get_resolution(ev.case_id)

    assert conflict is not None
    assert conflict.trigger_event == "assumed a tool existed that didn't"
    assert diagnosis is not None
    assert diagnosis.symptom_vs_cause == "hallucinated a tool call"
    assert resolution is not None
    assert resolution.fix_applied == "verify tool names against the live registry first"
    assert resolution.rollback_plan  # never empty -- ConflictCatalog enforces this


def test_record_mistake_case_is_reviewable_via_the_shared_catalog(tmp_path):
    """The whole point: this is a REAL, durable, three-actor-shared
    record (Kevin/Claude/Aria all read the same catalog), not a private
    log only the XP ledger can see."""
    from sovereign_agent.diagnosis import ConflictCatalog

    ev = record_mistake(
        what_happened="test mistake", how_to_avoid="test avoidance",
        data_dir=tmp_path,
    )
    catalog = ConflictCatalog(tmp_path / "diagnoses")
    all_cases = catalog.all_cases()
    assert any(c.case_id == ev.case_id for c in all_cases)
