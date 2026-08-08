"""Tests for M63 — ConformanceSentinel (naming discipline + standards enforcement).

446 lines of standards checking code, now finally tested.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_sentinel(tmp_path: Path, rules=None, repo_root=None):
    from sovereign_agent.stewardship.conformance_sentinel import ConformanceSentinel
    return ConformanceSentinel(
        data_dir=tmp_path,
        rules=rules if rules is not None else [],
        repo_root=repo_root or tmp_path,
    )


# ─── Registration ─────────────────────────────────────────────────────────────


def test_sentinel_id_is_conformance(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.id == "conformance"


def test_sentinel_registered_in_registry(tmp_path):
    from sovereign_agent.stewardship.registry import _REGISTRY
    from sovereign_agent.stewardship import conformance_sentinel  # noqa: F401
    assert "conformance" in _REGISTRY


# ─── Articles ─────────────────────────────────────────────────────────────────


def test_articles_non_empty(tmp_path):
    s = _make_sentinel(tmp_path)
    arts = s.articles()
    assert len(arts) >= 3


def test_articles_mention_propose_not_auto_fix(tmp_path):
    s = _make_sentinel(tmp_path)
    combined = " ".join(s.articles()).lower()
    assert "propose" in combined or "auto-fix" in combined or "never auto" in combined


# ─── Kill switch ─────────────────────────────────────────────────────────────


def test_kill_switch_env_correct(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.kill_switch_env == "SOV_NO_CONFORMANCE_SENTINEL"


def test_is_enabled_true_by_default(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.is_enabled() is True


def test_kill_switch_disables_sentinel(tmp_path, monkeypatch):
    monkeypatch.setenv("SOV_NO_CONFORMANCE_SENTINEL", "1")
    s = _make_sentinel(tmp_path)
    assert s.is_enabled() is False


# ─── Clean scan (no rules) ───────────────────────────────────────────────────


def test_scan_no_rules_returns_clean(tmp_path):
    s = _make_sentinel(tmp_path, rules=[])
    report = s.scan()
    assert report.sentinel_id == "conformance"
    assert report.findings_count == 0
    assert report.details["alerts"] == 0
    assert report.details["warnings"] == 0


def test_health_ok_with_no_violations(tmp_path):
    s = _make_sentinel(tmp_path, rules=[])
    status = s.health_status()
    assert status.level == "ok"


# ─── Kill-switch-documented rule ─────────────────────────────────────────────


def test_kill_switch_rule_detects_missing_doc(tmp_path):
    """A sentinel file without SOV_NO_ mention → violation."""
    from sovereign_agent.stewardship.conformance_sentinel import KillSwitchDocumentedRule

    # Create a fake sentinel file missing the kill switch doc
    fake_sentinel = tmp_path / "fake_sentinel.py"
    fake_sentinel.write_text("class FakeSentinel:\n    pass\n")

    rule = KillSwitchDocumentedRule()
    violations = rule.evaluate(tmp_path)
    paths = [v.path for v in violations]
    assert str(fake_sentinel) in paths


def test_kill_switch_rule_passes_when_documented(tmp_path):
    """A sentinel file with SOV_NO_ mention → no violation."""
    from sovereign_agent.stewardship.conformance_sentinel import KillSwitchDocumentedRule

    good_sentinel = tmp_path / "good_sentinel.py"
    good_sentinel.write_text(
        "# Kill switch: SOV_NO_GOOD_SENTINEL=1\nclass GoodSentinel:\n    pass\n"
    )

    rule = KillSwitchDocumentedRule()
    violations = rule.evaluate(tmp_path)
    paths = [v.path for v in violations]
    assert str(good_sentinel) not in paths


# ─── NoVagueName rule ────────────────────────────────────────────────────────


def test_vague_name_rule_detects_module_level_vague_name(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import NoVagueNameRule

    vague_file = tmp_path / "module.py"
    vague_file.write_text("data = {'key': 'value'}\n")

    rule = NoVagueNameRule()
    violations = rule.evaluate(tmp_path)
    names = [v.summary for v in violations]
    assert any("data" in n for n in names)


def test_vague_name_rule_passes_specific_names(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import NoVagueNameRule

    good_file = tmp_path / "specific.py"
    good_file.write_text("user_profile = {'key': 'value'}\n")

    rule = NoVagueNameRule()
    violations = rule.evaluate(tmp_path)
    paths = [v.path for v in violations]
    assert str(good_file) not in paths


# ─── ManifestArticles rule ───────────────────────────────────────────────────


def test_manifest_articles_rule_detects_too_few_articles(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import ManifestArticlesRule

    sparse_sentinel = tmp_path / "sparse_sentinel.py"
    sparse_sentinel.write_text(
        'def articles(self):\n    return [\n        "I. one article"\n    ]\n'
    )

    rule = ManifestArticlesRule()
    violations = rule.evaluate(tmp_path)
    paths = [v.path for v in violations]
    assert str(sparse_sentinel) in paths


# ─── Scan with violations ────────────────────────────────────────────────────


def test_scan_with_custom_warning_rule(tmp_path):
    """A custom rule that returns warnings → health level 'warning'."""
    from sovereign_agent.stewardship.conformance_sentinel import (
        ConformanceRule,
        RuleViolation,
    )

    class AlwaysWarningRule(ConformanceRule):
        name = "always-warn"
        description = "always warns"
        surface = "other"

        def evaluate(self, repo_root):
            return [
                RuleViolation(
                    rule_name=self.name,
                    severity="warning",
                    surface="other",
                    summary="synthetic warning",
                )
            ]

    s = _make_sentinel(tmp_path, rules=[AlwaysWarningRule()])
    report = s.scan()
    assert report.findings_count == 1
    assert report.details["warnings"] == 1
    assert report.details["alerts"] == 0


def test_health_warning_with_warning_rule(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import (
        ConformanceRule,
        RuleViolation,
    )

    class AlwaysWarningRule(ConformanceRule):
        name = "warn-rule"
        description = "warns"
        surface = "other"

        def evaluate(self, repo_root):
            return [RuleViolation(rule_name=self.name, severity="warning", surface="other", summary="w")]

    s = _make_sentinel(tmp_path, rules=[AlwaysWarningRule()])
    s.scan()  # health_status() reads the cache scan() writes — never re-scans itself
    assert s.health_status().level == "warning"


def test_health_error_with_alert_rule(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import (
        ConformanceRule,
        RuleViolation,
    )

    class AlwaysAlertRule(ConformanceRule):
        name = "alert-rule"
        description = "alerts"
        surface = "other"

        def evaluate(self, repo_root):
            return [RuleViolation(rule_name=self.name, severity="alert", surface="other", summary="a")]

    s = _make_sentinel(tmp_path, rules=[AlwaysAlertRule()])
    s.scan()  # health_status() reads the cache scan() writes — never re-scans itself
    assert s.health_status().level == "error"


# ─── Proposals not auto-fix ───────────────────────────────────────────────────


def test_scan_does_not_modify_source_files(tmp_path):
    """scan() must PROPOSE fixes; it must never edit source files."""
    from sovereign_agent.stewardship.conformance_sentinel import NoVagueNameRule

    vague_file = tmp_path / "vague_module.py"
    original = "data = {}\n"
    vague_file.write_text(original)

    s = _make_sentinel(tmp_path, rules=[NoVagueNameRule()])
    s.scan()

    # File must not have been modified
    assert vague_file.read_text() == original


# ─── Catalog persistence ─────────────────────────────────────────────────────


def test_scan_writes_violations_catalog(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import (
        ConformanceRule,
        RuleViolation,
    )

    class OneViolation(ConformanceRule):
        name = "one-violation"
        description = "one"
        surface = "other"

        def evaluate(self, repo_root):
            return [RuleViolation(rule_name=self.name, severity="warning", surface="other", summary="test")]

    s = _make_sentinel(tmp_path, rules=[OneViolation()])
    s.scan()
    cat_path = tmp_path / "sentinels" / "conformance" / "catalogs" / "violations.json"
    assert cat_path.exists()


# ─── Multiple rules ───────────────────────────────────────────────────────────


def test_multiple_rules_all_violations_collected(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import (
        ConformanceRule,
        RuleViolation,
    )

    class Rule1(ConformanceRule):
        name = "r1"; description = "r1"; surface = "other"
        def evaluate(self, r): return [RuleViolation(rule_name=self.name, severity="warning", surface="other", summary="v1")]

    class Rule2(ConformanceRule):
        name = "r2"; description = "r2"; surface = "other"
        def evaluate(self, r): return [RuleViolation(rule_name=self.name, severity="warning", surface="other", summary="v2")]

    s = _make_sentinel(tmp_path, rules=[Rule1(), Rule2()])
    report = s.scan()
    assert report.findings_count == 2


# ─── Pluggable rules ─────────────────────────────────────────────────────────


def test_custom_rule_registers_at_construction_without_editing_sentinel(tmp_path):
    """Adding a new rule does not require editing the sentinel source."""
    from sovereign_agent.stewardship.conformance_sentinel import (
        ConformanceRule,
        ConformanceSentinel,
        RuleViolation,
    )

    class MyCustomRule(ConformanceRule):
        name = "my-custom"; description = "custom"; surface = "other"
        def evaluate(self, r): return [RuleViolation(rule_name=self.name, severity="info", surface="other", summary="custom")]

    # Pass the rule at construction — no sentinel source edit required
    s = ConformanceSentinel(data_dir=tmp_path, rules=[MyCustomRule()], repo_root=tmp_path)
    report = s.scan()
    rule_names = [v["rule_name"] for v in report.details.get("violations", [])]
    assert "my-custom" in rule_names
