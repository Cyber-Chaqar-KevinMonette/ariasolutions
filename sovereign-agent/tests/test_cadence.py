"""Tests for the cadence channel — per-collaborator portraits."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sovereign_agent import cadence as _cad


# ─── SkillNode confidence decay ──────────────────────────────────────────


def test_skill_decay_zero_when_never_practiced():
    s = _cad.SkillNode(domain="python", name="lists", confidence=1.0)
    # last_practiced_at is empty → decay factor is 0 → current is 0
    assert s.current_confidence(_cad._iso_now()) == 0.0


def test_skill_decay_full_when_just_practiced():
    now = _cad._iso_now()
    s = _cad.SkillNode(
        domain="python", name="lists", confidence=0.8,
        first_observed_at=now, last_practiced_at=now,
    )
    assert s.current_confidence(now) == pytest.approx(0.8, abs=0.01)


def test_skill_decay_half_at_half_life():
    """At one half-life elapsed, displayed confidence halves."""
    now = datetime.now(timezone.utc)
    long_ago = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = _cad.SkillNode(
        domain="python", name="lists", confidence=0.8,
        first_observed_at=long_ago, last_practiced_at=long_ago,
    )
    decayed = s.current_confidence(now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert decayed == pytest.approx(0.4, abs=0.05)


# ─── Velocity EWMA ───────────────────────────────────────────────────────


def test_ewma_first_sample_becomes_baseline():
    profile = _cad.Profile(person_id="test")
    sample = _cad.VelocitySample(task_type="debug", duration_seconds=300.0)
    _cad.update_velocity_ewma(profile, sample)
    assert profile.velocity_ewma["debug"] == 300.0


def test_ewma_smooths_subsequent_samples():
    """alpha=0.3 means new sample contributes 30% to updated EWMA."""
    profile = _cad.Profile(person_id="test")
    _cad.update_velocity_ewma(profile, _cad.VelocitySample(task_type="debug", duration_seconds=100.0))
    _cad.update_velocity_ewma(profile, _cad.VelocitySample(task_type="debug", duration_seconds=200.0))
    # 0.3 * 200 + 0.7 * 100 = 130
    assert profile.velocity_ewma["debug"] == pytest.approx(130.0)


def test_ewma_resists_single_outlier():
    """After 5 samples around 100s, one wild 1000s sample shouldn't dominate."""
    profile = _cad.Profile(person_id="test")
    for _ in range(5):
        _cad.update_velocity_ewma(profile, _cad.VelocitySample(task_type="debug", duration_seconds=100.0))
    _cad.update_velocity_ewma(profile, _cad.VelocitySample(task_type="debug", duration_seconds=1000.0))
    # Outlier should pull EWMA up but not overwhelmingly
    assert profile.velocity_ewma["debug"] < 400.0


# ─── Breakthrough / struggle detection ───────────────────────────────────


def test_breakthrough_when_significantly_faster():
    profile = _cad.Profile(person_id="test")
    profile.velocity_ewma["debug"] = 300.0
    fast = _cad.VelocitySample(task_type="debug", duration_seconds=100.0)
    assert _cad.detect_breakthrough(profile, fast)


def test_no_breakthrough_without_prior():
    profile = _cad.Profile(person_id="test")
    sample = _cad.VelocitySample(task_type="debug", duration_seconds=50.0)
    assert not _cad.detect_breakthrough(profile, sample)


def test_struggle_when_significantly_slower():
    profile = _cad.Profile(person_id="test")
    profile.velocity_ewma["debug"] = 300.0
    slow = _cad.VelocitySample(task_type="debug", duration_seconds=900.0)
    assert _cad.detect_struggle(profile, slow)


def test_struggle_when_outcome_is_stuck_regardless_of_time():
    profile = _cad.Profile(person_id="test")
    profile.velocity_ewma["debug"] = 300.0
    fast_but_stuck = _cad.VelocitySample(
        task_type="debug", duration_seconds=50.0, outcome="stuck",
    )
    assert _cad.detect_struggle(profile, fast_but_stuck)


# ─── Forgetting curve / spaced repetition ────────────────────────────────


def test_successful_recall_doubles_half_life():
    profile = _cad.Profile(person_id="test")
    rc1 = _cad.record_recall(profile, "list-comprehension", "python", successful=True)
    assert rc1.half_life_days == 14.0  # 7 * 2
    rc2 = _cad.record_recall(profile, "list-comprehension", "python", successful=True)
    assert rc2.half_life_days == 28.0  # 14 * 2


def test_missed_recall_halves_half_life():
    profile = _cad.Profile(person_id="test")
    # Get half-life to 28 first
    _cad.record_recall(profile, "x", "domain", successful=True)
    _cad.record_recall(profile, "x", "domain", successful=True)
    # Now miss
    rc = _cad.record_recall(profile, "x", "domain", successful=False)
    assert rc.half_life_days == 14.0


def test_half_life_bounded():
    profile = _cad.Profile(person_id="test")
    # Many successes shouldn't exceed 365 days
    for _ in range(20):
        _cad.record_recall(profile, "x", "domain", successful=True)
    rc = profile.recalls["domain:x"]
    assert rc.half_life_days <= 365.0
    # Many misses shouldn't drop below 1 day
    for _ in range(20):
        _cad.record_recall(profile, "y", "domain", successful=False)
    rc2 = profile.recalls["domain:y"]
    assert rc2.half_life_days >= 1.0


def test_due_for_review_finds_overdue_concepts():
    profile = _cad.Profile(person_id="test")
    # Record a recall 60 days ago with a 7-day half-life
    old_iso = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile.recalls["domain:x"] = _cad.ConceptRecall(
        concept="x", domain="domain", last_recall_at=old_iso, half_life_days=7.0,
    )
    due = _cad.due_for_review(profile)
    assert len(due) == 1
    assert due[0].concept == "x"


# ─── Resonance detection ─────────────────────────────────────────────────


def test_resonance_finds_mastered_skills_in_other_domains():
    profile = _cad.Profile(person_id="test")
    profile.skills["music:fugue"] = _cad.SkillNode(
        domain="music", name="fugue", confidence=0.9, practice_count=10,
    )
    profile.skills["python:simple"] = _cad.SkillNode(
        domain="python", name="simple", confidence=0.5, practice_count=2,
    )
    new = _cad.SkillNode(domain="python", name="recursion", confidence=0.6)
    candidates = _cad.detect_resonance(profile, new, confidence_threshold=0.7)
    assert "music:fugue" in candidates
    assert "python:simple" not in candidates  # same domain, excluded


# ─── Stretch vector ──────────────────────────────────────────────────────


def test_stretch_vector_separates_frontier_from_mastered():
    profile = _cad.Profile(person_id="test", stretch_sigma=0.2)
    now = _cad._iso_now()
    profile.skills["python:lists"] = _cad.SkillNode(
        domain="python", name="lists", confidence=0.95,
        last_practiced_at=now,
    )
    profile.skills["python:decorators"] = _cad.SkillNode(
        domain="python", name="decorators", confidence=0.55,
        last_practiced_at=now,
    )
    sv = _cad.stretch_vector(profile, "python", now)
    assert "decorators" in sv["frontier_skills"]
    assert "lists" in sv["mastered_skills"]
    assert sv["reach_factor"] > 0


# ─── Persistence ─────────────────────────────────────────────────────────


def test_profile_roundtrips_through_json(tmp_path):
    profile = _cad.Profile(person_id="test", display_name="Test User", stretch_sigma=0.25)
    profile.learning_style = _cad.LearningStyle(kinetic=True, verbal=True, preferred_context_depth="deep")
    profile.skills["python:lists"] = _cad.SkillNode(
        domain="python", name="lists", confidence=0.7, practice_count=3,
    )
    profile.moments.append(_cad.Moment(type="breakthrough", domain="python", summary="got list comp"))
    _cad.save_profile(profile, tmp_path)
    loaded = _cad.load_profile("test", tmp_path)
    assert loaded is not None
    assert loaded.person_id == "test"
    assert loaded.stretch_sigma == 0.25
    assert loaded.learning_style.kinetic is True
    assert loaded.learning_style.preferred_context_depth == "deep"
    assert "python:lists" in loaded.skills
    assert loaded.skills["python:lists"].confidence == 0.7
    assert len(loaded.moments) == 1
    assert loaded.moments[0].type == "breakthrough"


def test_seed_default_operator_uses_kevin_style(tmp_path):
    """The default operator profile must reflect the stated style."""
    profile = _cad.seed_default_operator(tmp_path)
    assert profile.person_id == "operator"
    assert profile.learning_style.kinetic is True
    assert profile.learning_style.verbal is True
    assert profile.learning_style.ambient is True
    assert profile.learning_style.context_first is True
    assert profile.learning_style.preferred_context_depth == "deep"
    assert profile.stretch_sigma == 0.15


def test_seed_default_operator_is_idempotent(tmp_path):
    """Calling seed twice should not overwrite an existing profile."""
    profile = _cad.seed_default_operator(tmp_path)
    # Modify the profile
    profile.stretch_sigma = 0.99
    _cad.save_profile(profile, tmp_path)
    # Seeding again should return the modified version
    again = _cad.seed_default_operator(tmp_path)
    assert again.stretch_sigma == 0.99


def test_list_profiles_returns_all(tmp_path):
    for pid in ("alice", "bob", "carol"):
        _cad.save_profile(_cad.Profile(person_id=pid), tmp_path)
    profiles = _cad.list_profiles(tmp_path)
    assert {p.person_id for p in profiles} == {"alice", "bob", "carol"}
