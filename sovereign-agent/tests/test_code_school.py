"""Tests for code_school — curriculum integrity + spaced repetition."""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.code_school import drills as D
from sovereign_agent.code_school import lessons as L
from sovereign_agent.code_school import tracks as T

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def dd(tmp_path):
    return tmp_path


# ── tracks ─────────────────────────────────────────────────────────────
def test_only_the_decided_tracks_ship():
    """Same discipline as verticals.KEEP_SLUGS: defining a track is a draft,
    listing it in ENABLED is the decision. A ship-by-default catalog is how
    the shop reached 88 verticals with six working."""
    assert {t.slug for t in T.enabled_tracks()} == {"python", "aisys"}
    assert len(T.CATALOG) > len(T.enabled_tracks()), "drafts should exist"


def test_each_track_has_three_channels():
    for t in T.enabled_tracks():
        assert t.channels == (f"{t.slug}-lessons", f"{t.slug}-drills",
                              f"{t.slug}-review")


def test_track_lookup_is_case_insensitive():
    assert T.track_by_slug("PYTHON") is T.track_by_slug("python")
    assert T.track_by_slug("nope") is None


# ── curriculum integrity — the thing that stops lessons rotting ────────
def test_every_lesson_cites_a_file_that_exists():
    """A lesson pointing at a deleted file is fiction, and teaching Kevin
    something false about his own codebase is the one failure this whole
    module exists to avoid."""
    missing = [f"{ls.id} -> {ls.file}" for ls in L.LESSONS
               if not (REPO / ls.file).exists()]
    assert not missing, "lesson(s) citing a file that no longer exists: " + \
        "; ".join(missing)


def test_every_lesson_belongs_to_a_real_track():
    slugs = {t.slug for t in T.CATALOG}
    bad = [ls.id for ls in L.LESSONS if ls.track not in slugs]
    assert not bad, f"lesson(s) on an unknown track: {bad}"


def test_every_enabled_track_has_at_least_one_lesson():
    """Shipping a category with nothing in it is the empty-channel mistake
    we just spent the night undoing."""
    for t in T.enabled_tracks():
        assert L.for_track(t.slug), f"{t.slug} would ship empty"


def test_lesson_ids_are_unique():
    ids = [ls.id for ls in L.LESSONS]
    assert len(ids) == len(set(ids))


def test_every_named_drill_exists():
    dangling = [ls.drill for ls in L.LESSONS
                if ls.drill and D.by_id(ls.drill) is None]
    assert not dangling, f"lesson(s) naming a missing drill: {dangling}"


def test_every_drill_points_back_at_a_real_lesson():
    bad = [d.id for d in D.DRILLS if L.by_id(d.lesson) is None]
    assert not bad, f"drill(s) referencing a missing lesson: {bad}"


def test_lessons_are_ordered_deterministically():
    a = [ls.id for ls in L.ordered_for_track("python")]
    b = [ls.id for ls in L.ordered_for_track("python")]
    assert a == b and a


def test_every_lesson_states_a_principle():
    """symptom + reality without a transferable rule is an anecdote."""
    weak = [ls.id for ls in L.LESSONS if len(ls.principle) < 40]
    assert not weak, f"lesson(s) with no real principle: {weak}"


# ── spaced repetition ──────────────────────────────────────────────────
def test_intervals_expand():
    assert list(D.INTERVALS_DAYS) == sorted(D.INTERVALS_DAYS)
    assert D.INTERVALS_DAYS[0] <= 1.0, "first review must be soon"


def test_interval_grows_with_streak():
    assert D.next_interval_days(1) < D.next_interval_days(3)


def test_interval_saturates_rather_than_crashing():
    assert D.next_interval_days(999) == D.INTERVALS_DAYS[-1]
    assert D.next_interval_days(0) == D.INTERVALS_DAYS[0]


def test_passing_pushes_the_review_out(dd):
    now = 1_000_000.0
    r1 = D.record_attempt(dd, "fix-the-swallow", True, now=now)
    r2 = D.record_attempt(dd, "fix-the-swallow", True, now=now)
    assert r2["due_ts"] > r1["due_ts"], "a second pass should wait longer"


def test_failing_resets_the_streak_but_keeps_history(dd):
    now = 1_000_000.0
    D.record_attempt(dd, "fix-the-swallow", True, now=now)
    D.record_attempt(dd, "fix-the-swallow", True, now=now)
    rec = D.record_attempt(dd, "fix-the-swallow", False, now=now)
    assert rec["streak"] == 0
    assert rec["passes"] == 2, "history is kept — struggling is not erased"
    assert rec["attempts"] == 3
    assert rec["due_ts"] == D.schedule_after(0, now=now), "back tomorrow"


def test_new_drills_come_before_reviews(dd):
    """A learner who opens the app and sees only repeats loses the thread."""
    now = 1_000_000.0
    D.record_attempt(dd, "fix-the-swallow", True, now=now - 10 * 86400)
    due = D.due_drills(dd, "python", now=now)
    assert due, "something should be due"
    assert due[0].id != "fix-the-swallow", "unseen material first"
    assert any(d.id == "fix-the-swallow" for d in due), "overdue still appears"


def test_a_drill_not_yet_due_is_not_offered(dd):
    now = 1_000_000.0
    for d in D.for_track("python"):
        D.record_attempt(dd, d.id, True, now=now)
    assert D.due_drills(dd, "python", now=now + 60) == []


def test_progress_counts_only_passes(dd):
    now = 1_000_000.0
    D.record_attempt(dd, "fix-the-swallow", False, now=now)
    p = D.progress(dd, "python")
    assert p["passed"] == 0 and p["attempts"] == 1
    D.record_attempt(dd, "fix-the-swallow", True, now=now)
    assert D.progress(dd, "python")["passed"] == 1


def test_corrupt_progress_file_degrades_quietly(dd):
    D.state_path(dd).write_text("{not json", encoding="utf-8")
    assert D.progress(dd)["passed"] == 0
    assert D.record_attempt(dd, "fix-the-swallow", True, now=1.0)["passes"] == 1


# ── xp ─────────────────────────────────────────────────────────────────
from sovereign_agent import code_learning_xp as X  # noqa: E402


def test_recovering_from_failure_scores_more_than_a_clean_pass(dd):
    """The drills you struggle with are the ones you're learning. A system
    that scores only clean successes teaches you to avoid hard things."""
    assert X.XP_DRILL_RECOVERED > X.XP_DRILL_PASSED


def test_reading_is_worth_far_less_than_doing(dd):
    assert X.XP_LESSON_READ * 3 < X.XP_DRILL_PASSED


def test_unknown_events_are_refused_not_guessed(dd):
    """An invented number is worse than no number."""
    assert X.award(dd, "made_up_event", "x") is None
    assert X.total_xp(dd) == 0


def test_awards_accumulate_and_level(dd):
    for _ in range(9):
        X.award(dd, "drill_passed", "fix-the-swallow", track="python")
    s = X.summary(dd, "python")
    assert s["xp"] == 9 * X.XP_DRILL_PASSED
    assert s["level"] == X.level_for(s["xp"]) >= 2
    assert s["by_event"]["drill_passed"] == 9


def test_track_filter_separates_curricula(dd):
    X.award(dd, "drill_passed", "a", track="python")
    X.award(dd, "drill_passed", "b", track="aisys")
    assert X.total_xp(dd, "python") == X.XP_DRILL_PASSED
    assert X.total_xp(dd) == 2 * X.XP_DRILL_PASSED


def test_a_corrupt_ledger_line_does_not_lose_the_rest(dd):
    X.award(dd, "drill_passed", "a", track="python")
    with open(X.ledger_path(dd), "a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
    X.award(dd, "drill_passed", "b", track="python")
    assert X.total_xp(dd) == 2 * X.XP_DRILL_PASSED
