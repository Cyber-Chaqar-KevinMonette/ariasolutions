"""Tests for work_suggestions — grounded "what should I work on?" ideas.

Kevin, 2026-07-26: "she could give me a list of important and/or
valuable task she can work on or practice doing." Every suggestion must
trace to real state (a sentinel's own proposal/gap, or a real unbuilt
bot project) — nothing invented, and an empty scan is an honest empty
list.
"""
from __future__ import annotations

import pytest

from sovereign_agent.work_suggestions import (
    WorkSuggestion,
    compose_suggestions_report,
    gather_suggestions,
    is_suggestions_query,
)


@pytest.fixture(autouse=True)
def _no_real_repo_scan(monkeypatch, tmp_path_factory):
    """gather_suggestions's apply-queue source scans aria-*/ dirs at the
    real repo root — irrelevant to these tests and would inject
    unpredictable real-repo state into exact-count assertions below. Point
    _repo_root() at an empty scratch dir instead of neutralizing the whole
    function, so the dedicated apply-queue tests below (which pass
    repo_root= explicitly, bypassing _repo_root() entirely) still exercise
    the real scan logic."""
    from sovereign_agent import work_suggestions
    empty_root = tmp_path_factory.mktemp("no_aria_dirs_here")
    monkeypatch.setattr(work_suggestions, "_repo_root", lambda: empty_root)


def test_as_goal_text_includes_remediation_when_present():
    s = WorkSuggestion(source="cache", kind="fix", summary="stale pyc files",
                       remediation="clean the pycache")
    assert s.as_goal_text() == "stale pyc files — clean the pycache"


def test_as_goal_text_falls_back_to_summary_only():
    s = WorkSuggestion(source="cache", kind="fix", summary="stale pyc files")
    assert s.as_goal_text() == "stale pyc files"


def test_emoji_is_distinct_per_kind():
    fix = WorkSuggestion(source="x", kind="fix", summary="a")
    gap = WorkSuggestion(source="x", kind="gap", summary="a")
    build = WorkSuggestion(source="x", kind="build", summary="a")
    assert len({fix.emoji, gap.emoji, build.emoji}) == 3


def test_sentinel_proposal_becomes_a_fix_suggestion(monkeypatch, tmp_path):
    from sovereign_agent import work_suggestions

    class FakeSentinel:
        id = "fake"

        def bootstrap(self): pass
        def is_enabled(self): return True
        def scan(self): return object()
        def proposals(self, report):
            return [{"summary": "widget is broken", "remediation": "fix the widget"}]
        def coverage_gaps(self, report):
            return []

    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [FakeSentinel()])

    items = gather_suggestions(tmp_path)
    assert len(items) == 1
    assert items[0].kind == "fix"
    assert items[0].source == "fake"
    assert items[0].summary == "widget is broken"
    assert items[0].remediation == "fix the widget"


def test_a_crashing_sentinel_never_blocks_the_others(monkeypatch, tmp_path):
    from sovereign_agent import work_suggestions

    class BadSentinel:
        id = "bad"
        def bootstrap(self): raise RuntimeError("boom")

    class GoodSentinel:
        id = "good"
        def bootstrap(self): pass
        def is_enabled(self): return True
        def scan(self): return object()
        def proposals(self, report):
            return [{"summary": "real finding"}]
        def coverage_gaps(self, report):
            return []

    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [BadSentinel(), GoodSentinel()])

    items = gather_suggestions(tmp_path)
    assert len(items) == 1
    assert items[0].summary == "real finding"


def test_disabled_sentinel_contributes_nothing(monkeypatch, tmp_path):
    class DisabledSentinel:
        id = "off"
        def bootstrap(self): pass
        def is_enabled(self): return False

    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [DisabledSentinel()])

    assert gather_suggestions(tmp_path) == []


def test_concept_bot_project_becomes_a_build_suggestion(monkeypatch, tmp_path):
    from sovereign_agent import bot_projects

    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [])

    bot_projects.save(bot_projects.BotProject(
        project_name="Idea Bot", kind="notification-feed",
        description="a cool idea", status="concept"), tmp_path)
    bot_projects.save(bot_projects.BotProject(
        project_name="Built Bot", kind="notification-feed",
        description="already live", status="live"), tmp_path)

    items = gather_suggestions(tmp_path)
    assert len(items) == 1
    assert items[0].kind == "build"
    assert "Idea Bot" in items[0].summary


def test_empty_state_produces_an_honest_empty_report(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [])
    from sovereign_agent import bot_projects
    monkeypatch.setattr(bot_projects, "list_all", lambda d: [])

    assert gather_suggestions(tmp_path) == []
    report = compose_suggestions_report(tmp_path)
    assert "nothing" in report.lower() or "clean" in report.lower()


def _seed_module(root, name, *, applied_ok=False, has_backups=False, has_test=False):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "apply_x.sh").write_text("#!/usr/bin/env bash\n")
    if applied_ok:
        (d / ".applied_ok").write_text("ok\n")
    if has_backups:
        (d / "backups").mkdir(exist_ok=True)
    if has_test:
        (root / "tests").mkdir(exist_ok=True)
        slug = name.removeprefix("aria-").replace("-", "_")
        (root / "tests" / f"test_{slug}.py").write_text("")


def test_apply_queue_pending_module_becomes_a_build_suggestion(tmp_path):
    from sovereign_agent.work_suggestions import _apply_queue_suggestions

    _seed_module(tmp_path, "aria-pending-thing")
    items = _apply_queue_suggestions(repo_root=tmp_path)
    assert len(items) == 1
    assert items[0].kind == "build"
    assert items[0].source == "apply-queue"
    assert "aria-pending-thing" in items[0].summary


def test_apply_queue_skips_applied_modules(tmp_path):
    from sovereign_agent.work_suggestions import _apply_queue_suggestions

    _seed_module(tmp_path, "aria-done-via-marker", applied_ok=True)
    _seed_module(tmp_path, "aria-done-via-backups", has_backups=True)
    _seed_module(tmp_path, "aria-done-via-test", has_test=True)
    assert _apply_queue_suggestions(repo_root=tmp_path) == []


def test_apply_queue_ignores_dirs_without_an_apply_script(tmp_path):
    from sovereign_agent.work_suggestions import _apply_queue_suggestions

    (tmp_path / "aria-no-apply-script").mkdir()
    assert _apply_queue_suggestions(repo_root=tmp_path) == []


def test_open_conflict_case_becomes_a_fix_suggestion(monkeypatch, tmp_path):
    from sovereign_agent.diagnosis import ConflictCatalog

    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [])
    catalog = ConflictCatalog(tmp_path / "diagnoses")
    catalog.open_conflict(type="drift", trigger_event="tests red on main",
                          actor="claude")

    items = gather_suggestions(tmp_path)
    assert len(items) == 1
    assert items[0].kind == "fix"
    assert items[0].source == "diagnosis"
    assert "tests red on main" in items[0].summary


def test_resolved_conflict_case_is_not_suggested(monkeypatch, tmp_path):
    from sovereign_agent.diagnosis import ConflictCatalog

    monkeypatch.setattr(
        "sovereign_agent.stewardship.registry.instantiate_all",
        lambda data_dir: [])
    catalog = ConflictCatalog(tmp_path / "diagnoses")
    case = catalog.open_conflict(type="drift", trigger_event="tests red",
                                 actor="claude")
    catalog._set_status(case.case_id, "resolved")

    assert gather_suggestions(tmp_path) == []


def test_is_suggestions_query_matches_natural_phrasing():
    assert is_suggestions_query("what should you work on?")
    assert is_suggestions_query("give me some suggestions")
    assert not is_suggestions_query("what's the weather")
