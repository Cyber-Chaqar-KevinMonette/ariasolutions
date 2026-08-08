"""Tests for M63 — DefenseSentinel (pressure classification + posture playbooks).

414 lines of safety-critical pressure handling, now finally tested.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_sentinel(tmp_path: Path):
    from sovereign_agent.stewardship.defense_sentinel import DefenseSentinel
    return DefenseSentinel(data_dir=tmp_path)


def _make_event(threat_class: str, severity: str = "alert", reported_by: str = "test"):
    from sovereign_agent.stewardship.defense_sentinel import PressureEvent
    return PressureEvent.new(
        reported_by=reported_by,
        threat_class=threat_class,
        severity=severity,
        summary=f"test event: {threat_class}",
    )


# ─── Registration ─────────────────────────────────────────────────────────────


def test_sentinel_id_is_defense(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.id == "defense"


def test_sentinel_registered_in_registry(tmp_path):
    from sovereign_agent.stewardship.registry import _REGISTRY
    from sovereign_agent.stewardship import defense_sentinel  # noqa: F401
    assert "defense" in _REGISTRY


# ─── Articles ─────────────────────────────────────────────────────────────────


def test_articles_non_empty(tmp_path):
    s = _make_sentinel(tmp_path)
    arts = s.articles()
    assert len(arts) >= 3


def test_articles_mention_no_offensive_action(tmp_path):
    s = _make_sentinel(tmp_path)
    combined = " ".join(s.articles()).lower()
    assert "offensive" in combined or "retaliat" in combined or "harm" in combined


# ─── Kill switch ─────────────────────────────────────────────────────────────


def test_kill_switch_env_correct(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.kill_switch_env == "SOV_NO_DEFENSE_SENTINEL"


def test_is_enabled_true_by_default(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.is_enabled() is True


def test_kill_switch_disables_sentinel(tmp_path, monkeypatch):
    monkeypatch.setenv("SOV_NO_DEFENSE_SENTINEL", "1")
    s = _make_sentinel(tmp_path)
    assert s.is_enabled() is False


# ─── Clean scan (no events) ───────────────────────────────────────────────────


def test_scan_no_events_clean(tmp_path):
    s = _make_sentinel(tmp_path)
    report = s.scan()
    assert report.sentinel_id == "defense"
    assert report.findings_count == 0
    assert report.details["total_pressure_events"] == 0


def test_health_ok_with_no_events(tmp_path):
    s = _make_sentinel(tmp_path)
    status = s.health_status()
    assert status.level == "ok"
    assert status.sentinel_id == "defense"


# ─── Posture classification ───────────────────────────────────────────────────


def test_prompt_injection_maps_to_refuse(tmp_path):
    s = _make_sentinel(tmp_path)
    playbook = s.report_pressure(_make_event("prompt-injection"))
    assert playbook.posture == "REFUSE"


def test_resource_exhaustion_maps_to_quiesce(tmp_path):
    s = _make_sentinel(tmp_path)
    playbook = s.report_pressure(_make_event("resource-exhaustion"))
    assert playbook.posture == "QUIESCE"


def test_integrity_attack_maps_to_lockdown(tmp_path):
    s = _make_sentinel(tmp_path)
    playbook = s.report_pressure(_make_event("integrity-attack"))
    assert playbook.posture == "LOCKDOWN"


def test_confused_deputy_maps_to_witness(tmp_path):
    s = _make_sentinel(tmp_path)
    playbook = s.report_pressure(_make_event("confused-deputy"))
    assert playbook.posture == "WITNESS"


def test_social_engineering_maps_to_consult(tmp_path):
    s = _make_sentinel(tmp_path)
    playbook = s.report_pressure(_make_event("social-engineering-operator"))
    assert playbook.posture == "CONSULT"


def test_unknown_threat_maps_to_report(tmp_path):
    """Unknown pressure defaults to REPORT — visibility without action."""
    s = _make_sentinel(tmp_path)
    playbook = s.report_pressure(_make_event("unknown"))
    assert playbook.posture == "REPORT"


# ─── Catalog is append-only ───────────────────────────────────────────────────


def test_pressure_event_written_to_catalog(tmp_path):
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("prompt-injection"))
    catalog_path = tmp_path / "sentinels" / "defense" / "catalogs" / "pressure_events.jsonl"
    assert catalog_path.exists()
    lines = [l for l in catalog_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1


def test_catalog_is_append_only(tmp_path):
    """Two events → two lines; catalog never overwrites previous entries."""
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("prompt-injection"))
    s.report_pressure(_make_event("resource-exhaustion"))
    catalog_path = tmp_path / "sentinels" / "defense" / "catalogs" / "pressure_events.jsonl"
    lines = [l for l in catalog_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_repeated_scan_does_not_overwrite_catalog(tmp_path):
    """scan() reads the catalog; it must not truncate it."""
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("integrity-attack"))
    lines_before = (
        (tmp_path / "sentinels" / "defense" / "catalogs" / "pressure_events.jsonl")
        .read_text()
        .strip()
        .splitlines()
    )
    s.scan()
    lines_after = (
        (tmp_path / "sentinels" / "defense" / "catalogs" / "pressure_events.jsonl")
        .read_text()
        .strip()
        .splitlines()
    )
    assert len(lines_after) == len(lines_before)


# ─── Health status after critical postures ────────────────────────────────────


def test_health_warning_after_lockdown(tmp_path):
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("integrity-attack"))
    status = s.health_status()
    assert status.level == "warning"


def test_health_warning_after_quiesce(tmp_path):
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("resource-exhaustion"))
    status = s.health_status()
    assert status.level == "warning"


def test_health_ok_after_refuse_only(tmp_path):
    """REFUSE is not a critical posture — health stays ok."""
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("prompt-injection"))
    status = s.health_status()
    assert status.level == "ok"


# ─── Scan after events ────────────────────────────────────────────────────────


def test_scan_counts_events_correctly(tmp_path):
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("prompt-injection"))
    s.report_pressure(_make_event("resource-exhaustion"))
    report = s.scan()
    assert report.findings_count == 2
    assert report.details["total_pressure_events"] == 2


def test_scan_by_posture_breakdown(tmp_path):
    s = _make_sentinel(tmp_path)
    s.report_pressure(_make_event("prompt-injection"))
    s.report_pressure(_make_event("integrity-attack"))
    report = s.scan()
    by_posture = report.details["by_posture"]
    assert by_posture.get("REFUSE", 0) == 1
    assert by_posture.get("LOCKDOWN", 0) == 1


# ─── Corrupted catalog ────────────────────────────────────────────────────────


def test_scan_handles_corrupted_catalog_line(tmp_path):
    """A bad JSON line in the catalog must not crash scan()."""
    cat_dir = tmp_path / "sentinels" / "defense" / "catalogs"
    cat_dir.mkdir(parents=True)
    cat_path = cat_dir / "pressure_events.jsonl"
    cat_path.write_text("not valid json\n")
    s = _make_sentinel(tmp_path)
    report = s.scan()  # must not raise
    assert report.sentinel_id == "defense"
