"""Tests for member_levels — the activity XP system."""
from __future__ import annotations

import pytest

from sovereign_agent.member_levels import (
    COOLDOWN_S, award, get, leaderboard, level_for_xp, levels_path,
    xp_for_next, xp_into_level, xp_to_reach)


@pytest.fixture()
def dd(tmp_path):
    return tmp_path


# ── the curve ──────────────────────────────────────────────────────────
def test_level_zero_is_free():
    assert xp_to_reach(0) == 0
    assert level_for_xp(0) == 0


def test_curve_is_strictly_increasing():
    """Each level must cost more than the last, or later levels stop
    meaning anything."""
    costs = [xp_to_reach(n + 1) - xp_to_reach(n) for n in range(20)]
    assert costs == sorted(costs)
    assert len(set(costs)) > 1          # genuinely curved, not linear


def test_first_level_is_reachable_on_day_one():
    """A new member should see progress immediately — level 1 inside a
    handful of messages, not a grind."""
    assert xp_to_reach(1) <= 120


def test_level_for_xp_is_monotone():
    last = 0
    for xp in range(0, 5000, 37):
        lvl = level_for_xp(xp)
        assert lvl >= last
        last = lvl


def test_level_boundaries_are_exact():
    for n in (1, 2, 5, 12):
        assert level_for_xp(xp_to_reach(n)) == n
        assert level_for_xp(xp_to_reach(n) - 1) == n - 1


def test_progress_helpers_agree_with_the_curve():
    xp = xp_to_reach(3) + 10
    assert xp_into_level(xp) == 10
    assert xp_for_next(xp) == xp_to_reach(4) - xp


def test_negative_and_junk_xp_never_crash():
    for bad in (-50, None, 0):
        assert level_for_xp(bad) == 0


# ── awarding ───────────────────────────────────────────────────────────
def test_award_grants_and_persists(dd):
    r = award(dd, "u1", now=1000.0, amount=20)
    assert r["xp"] == 20 and r["gained"] == 20
    assert get(dd, "u1")["xp"] == 20


def test_cooldown_blocks_a_second_message(dd):
    assert award(dd, "u1", now=1000.0, amount=20) is not None
    assert award(dd, "u1", now=1000.0 + COOLDOWN_S - 1, amount=20) is None


def test_cooldown_expires(dd):
    award(dd, "u1", now=1000.0, amount=20)
    r = award(dd, "u1", now=1000.0 + COOLDOWN_S, amount=20)
    assert r is not None and r["xp"] == 40


def test_spamming_cannot_farm_the_leaderboard(dd):
    """The whole reason the cooldown exists: 100 rapid messages must not
    beat someone who chatted steadily."""
    for i in range(100):
        award(dd, "spammer", now=1000.0 + i * 0.5, amount=25)
    for i in range(5):
        award(dd, "regular", now=1000.0 + i * COOLDOWN_S, amount=20)
    assert get(dd, "spammer")["xp"] < get(dd, "regular")["xp"]


def test_level_up_is_reported_only_on_transition(dd):
    now = 1000.0
    seen = 0
    for i in range(12):
        r = award(dd, "u1", now=now + i * COOLDOWN_S, amount=25)
        if r and r["leveled_up"]:
            seen += 1
    assert seen >= 1
    assert seen == get(dd, "u1")["level"]


def test_message_count_tracks_awards_not_attempts(dd):
    award(dd, "u1", now=1000.0, amount=20)
    award(dd, "u1", now=1001.0, amount=20)      # cooled down, ignored
    assert get(dd, "u1")["messages"] == 1


def test_unknown_member_is_level_zero(dd):
    assert get(dd, "nobody") == {"xp": 0, "level": 0, "messages": 0,
                                 "into_level": 0, "to_next": xp_to_reach(1)}


def test_leaderboard_ranks_by_xp(dd):
    award(dd, "low", now=1000.0, amount=20)
    award(dd, "high", now=1000.0, amount=500)
    award(dd, "mid", now=1000.0, amount=100)
    assert [r["user_id"] for r in leaderboard(dd)] == ["high", "mid", "low"]


def test_corrupt_store_degrades_to_zero_not_a_crash(dd):
    """A bad file must never raise on the message path — that would take
    the gateway down."""
    levels_path(dd).write_text("{not json", encoding="utf-8")
    assert get(dd, "u1")["xp"] == 0
    assert award(dd, "u1", now=1000.0, amount=20) is not None
