"""Behavior tests for aria-safe-interval-stop (Workstream N) — prove:
  1. RunBudget's new safety_margin_seconds defaults to 0 (old behavior exactly
     preserved for every existing caller that doesn't set it).
  2. effective_wall_limit() gives a loop room to finish before the real
     deadline, floored at 0.
  3. WorkIntervalConfig floors the margin at a sane minimum.
  4. interval_boundary_reached() fires at the MARGINED boundary, not the
     hard deadline — and never fires for a non-active session.
  5. stop_at_safe_point() always produces a real, resumable checkpoint.
  6. resume_work_interval() refuses to resume without explicit approval —
     via direct approved=True OR via interrupts.request_resume() — and
     refuses no matter how much wall-clock time has passed since the pause.
"""
from __future__ import annotations

import pytest

from sovereign_agent.modes import RunBudget, effective_wall_limit
from sovereign_agent.work_interval import (
    DEFAULT_SAFETY_MARGIN_SECONDS,
    MIN_SAFETY_MARGIN_SECONDS,
    WorkIntervalConfig,
    interval_boundary_reached,
    resume_work_interval,
    stop_at_safe_point,
)
from sovereign_agent.autonomy.session import AutonomySession, start_block
import sovereign_agent.interrupts as interrupts


# ─── RunBudget / effective_wall_limit ──────────────────────────────────────


def test_default_safety_margin_is_zero_preserves_old_behavior():
    budget = RunBudget(max_wall_seconds=1800)
    assert budget.safety_margin_seconds == 0
    assert effective_wall_limit(budget) == 1800


def test_effective_wall_limit_subtracts_margin():
    budget = RunBudget(max_wall_seconds=3600, safety_margin_seconds=600)
    assert effective_wall_limit(budget) == 3000


def test_effective_wall_limit_floors_at_zero():
    budget = RunBudget(max_wall_seconds=100, safety_margin_seconds=500)
    assert effective_wall_limit(budget) == 0


# ─── WorkIntervalConfig ─────────────────────────────────────────────────────


def test_config_defaults_to_one_hour_interval():
    config = WorkIntervalConfig()
    assert config.interval_seconds == 3600
    assert config.safety_margin_seconds == DEFAULT_SAFETY_MARGIN_SECONDS


def test_config_floors_margin_at_minimum():
    config = WorkIntervalConfig(interval_seconds=120, safety_margin_seconds=5)
    assert config.safety_margin_seconds == MIN_SAFETY_MARGIN_SECONDS


def test_config_as_run_budget_carries_interval_and_margin():
    config = WorkIntervalConfig(interval_seconds=1800, safety_margin_seconds=200)
    budget = config.as_run_budget(max_iterations=99)
    assert budget.max_wall_seconds == 1800
    assert budget.safety_margin_seconds == 200
    assert budget.max_iterations == 99


# ─── interval_boundary_reached ──────────────────────────────────────────────


def _active_session(ttl_seconds: int = 3600) -> AutonomySession:
    session = AutonomySession(session_id="as-test", plan_id="plan-test", ttl_seconds=ttl_seconds)
    return start_block(session, approved=True)


def test_boundary_not_reached_well_within_lease():
    session = _active_session(ttl_seconds=3600)
    config = WorkIntervalConfig(interval_seconds=3600, safety_margin_seconds=60)
    assert interval_boundary_reached(session, config) is False


def test_boundary_reached_once_inside_margin():
    session = _active_session(ttl_seconds=30)
    config = WorkIntervalConfig(interval_seconds=30, safety_margin_seconds=3600)
    # margin (3600s) dwarfs the whole lease, so remaining time is always <= margin
    assert interval_boundary_reached(session, config) is True


def test_boundary_never_reached_for_inactive_session():
    session = AutonomySession(session_id="as-idle", plan_id="plan-test")  # status="proposed"
    config = WorkIntervalConfig()
    assert interval_boundary_reached(session, config) is False


# ─── stop_at_safe_point ─────────────────────────────────────────────────────


def test_stop_at_safe_point_produces_a_real_checkpoint():
    session = _active_session()
    stop_at_safe_point(session, done="wrote module X", next_up="verify module X", notes="mid-sprint")
    assert session.status == "paused"
    assert session.checkpoint["done"] == "wrote module X"
    assert session.checkpoint["next"] == "verify module X"
    assert session.checkpoint["notes"] == "mid-sprint"
    assert "paused_at" in session.checkpoint


# ─── resume_work_interval — the never-auto-resume guarantee ────────────────


def test_resume_refused_without_any_approval():
    session = _active_session()
    stop_at_safe_point(session, done="d", next_up="n")
    with pytest.raises(PermissionError):
        resume_work_interval(session)


def test_resume_refused_even_long_after_pause_with_no_approval_call(monkeypatch):
    session = _active_session()
    stop_at_safe_point(session, done="d", next_up="n")
    # Simulate a long time having passed since the pause — no approval call
    # was ever made. Elapsed time alone must never unlock resume.
    monkeypatch.setattr(
        "sovereign_agent.autonomy.session._now",
        lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        + __import__("datetime").timedelta(days=3),
    )
    with pytest.raises(PermissionError):
        resume_work_interval(session)


def test_resume_succeeds_with_explicit_approved_true():
    session = _active_session()
    stop_at_safe_point(session, done="d", next_up="n")
    resumed = resume_work_interval(session, approved=True)
    assert resumed.status == "active"


def test_resume_succeeds_via_interrupts_request_resume():
    # config_dir isolation comes from the autouse isolated_paths fixture in
    # this module's conftest.py — interrupts.py's flag files land in a fresh
    # tmp dir per test, never a real install's ~/.config/sovereign-agent/.
    session = _active_session()
    stop_at_safe_point(session, done="d", next_up="n")

    # No approval yet: refused.
    with pytest.raises(PermissionError):
        resume_work_interval(session)

    # Operator takes the one explicit, separately-timestamped action.
    interrupts.request_resume()
    resumed = resume_work_interval(session)
    assert resumed.status == "active"
