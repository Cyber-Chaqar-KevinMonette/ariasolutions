"""Tests for health.py — system health scanner (M82).

Covers: HealthReport.ok/by_severity/summary_line, _parse_iso_to_seconds,
scan_idle_cycles (EC-DREAM-006 detection), scan_zombies (EC-HEALTH-001),
plan_repairs (repair action mapping), and apply_repairs dry-run.

All tests use minimal in-memory mock objects — no filesystem side-effects.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import pytest

from sovereign_agent.health import (
    HealthFinding,
    HealthReport,
    RepairAction,
    _parse_iso_to_seconds,
    apply_repairs,
    plan_repairs,
    scan_idle_cycles,
    scan_zombies,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ago_iso(seconds: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _finding(
    edge_case_id: str = "EC-TEST-001",
    severity: str = "warn",
    target: str = "target-001",
    target_kind: str = "continuation",
    summary: str = "test finding",
    details: dict | None = None,
) -> HealthFinding:
    return HealthFinding(
        edge_case_id=edge_case_id,
        severity=severity,
        target=target,
        target_kind=target_kind,
        summary=summary,
        details=details or {},
    )


@dataclass
class _FakeCycle:
    atoms_written: int = 0
    files_written: int = 0


@dataclass
class _FakeDream:
    dream_id: str = "dream-001"
    status: str = "active"
    cycles: list[_FakeCycle] = field(default_factory=list)


class _FakeDreamStore:
    def __init__(self, dreams: list[_FakeDream]):
        self._dreams = dreams

    def list_all(self, status: str | None = None):
        if status is None:
            return self._dreams
        return [d for d in self._dreams if d.status == status]


@dataclass
class _FakeCont:
    task_id: str = "cont-001"
    status: str = "in_progress"
    planner: str = "test-planner"
    updated_at: str = field(default_factory=_now_iso)


class _FakeContStore:
    def __init__(self, conts: list[_FakeCont]):
        self._conts = conts

    def list_all(self, status: str | None = None):
        if status is None:
            return self._conts
        return [c for c in self._conts if c.status == status]


# ── HealthReport ──────────────────────────────────────────────────────────────


def test_health_report_ok_when_no_findings():
    report = HealthReport()
    assert report.ok is True


def test_health_report_ok_with_only_warn_findings():
    report = HealthReport(findings=[_finding(severity="warn")])
    assert report.ok is True


def test_health_report_ok_with_only_info_findings():
    report = HealthReport(findings=[_finding(severity="info")])
    assert report.ok is True


def test_health_report_not_ok_with_error_finding():
    report = HealthReport(findings=[_finding(severity="error")])
    assert report.ok is False


def test_health_report_not_ok_with_critical_finding():
    report = HealthReport(findings=[_finding(severity="critical")])
    assert report.ok is False


def test_health_report_summary_line_no_findings():
    report = HealthReport()
    assert report.summary_line() == "no issues found"


def test_health_report_summary_line_single():
    report = HealthReport(findings=[_finding(severity="warn")])
    line = report.summary_line()
    assert "1 findings" in line
    assert "warn" in line


def test_health_report_summary_line_multi_severity():
    findings = [
        _finding(severity="warn"),
        _finding(severity="warn"),
        _finding(severity="error"),
    ]
    report = HealthReport(findings=findings)
    line = report.summary_line()
    assert "3 findings" in line
    assert "2 warn" in line
    assert "1 error" in line


def test_health_report_by_severity():
    findings = [
        _finding(severity="warn", target="a"),
        _finding(severity="error", target="b"),
        _finding(severity="warn", target="c"),
    ]
    report = HealthReport(findings=findings)
    warns = report.by_severity("warn")
    assert len(warns) == 2
    errors = report.by_severity("error")
    assert len(errors) == 1
    assert errors[0].target == "b"


# ── _parse_iso_to_seconds ─────────────────────────────────────────────────────


def test_parse_iso_empty_returns_none():
    assert _parse_iso_to_seconds("") is None


def test_parse_iso_none_string_returns_none():
    assert _parse_iso_to_seconds(None) is None  # type: ignore[arg-type]


def test_parse_iso_valid_z_suffix():
    result = _parse_iso_to_seconds("2026-06-18T12:00:00Z")
    assert result is not None
    assert result > 0


def test_parse_iso_with_microseconds():
    result = _parse_iso_to_seconds("2026-06-18T12:00:00.123456Z")
    assert result is not None


def test_parse_iso_invalid_format_returns_none():
    assert _parse_iso_to_seconds("not-a-timestamp") is None


def test_parse_iso_recent_timestamp_close_to_now():
    now = datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    result = _parse_iso_to_seconds(iso)
    assert result is not None
    assert abs(result - now.timestamp()) < 2.0


# ── scan_idle_cycles ──────────────────────────────────────────────────────────


def test_scan_idle_cycles_no_findings_when_few_cycles():
    dream = _FakeDream(cycles=[_FakeCycle(files_written=0), _FakeCycle(files_written=0)])
    store = _FakeDreamStore([dream])
    # Window is 3, only 2 cycles → no finding
    findings = scan_idle_cycles(store, window=3, atom_threshold=1)
    assert findings == []


def test_scan_idle_cycles_fires_ec_dream_006():
    idle_cycles = [_FakeCycle(files_written=0) for _ in range(3)]
    dream = _FakeDream(cycles=idle_cycles)
    store = _FakeDreamStore([dream])
    findings = scan_idle_cycles(store, window=3, atom_threshold=1)
    assert len(findings) == 1
    assert findings[0].edge_case_id == "EC-DREAM-006"
    assert findings[0].target == "dream-001"


def test_scan_idle_cycles_skips_active_cycle():
    cycles = [
        _FakeCycle(files_written=0),
        _FakeCycle(files_written=5),  # active cycle — not idle
        _FakeCycle(files_written=0),
    ]
    dream = _FakeDream(cycles=cycles)
    store = _FakeDreamStore([dream])
    findings = scan_idle_cycles(store, window=3, atom_threshold=1)
    assert findings == []


def test_scan_idle_cycles_exactly_at_threshold():
    # files_written == atom_threshold (1) → still idle (≤ threshold)
    cycles = [_FakeCycle(files_written=1) for _ in range(3)]
    dream = _FakeDream(cycles=cycles)
    store = _FakeDreamStore([dream])
    findings = scan_idle_cycles(store, window=3, atom_threshold=1)
    assert len(findings) == 1


def test_scan_idle_cycles_above_threshold_not_idle():
    cycles = [_FakeCycle(files_written=2) for _ in range(3)]
    dream = _FakeDream(cycles=cycles)
    store = _FakeDreamStore([dream])
    findings = scan_idle_cycles(store, window=3, atom_threshold=1)
    assert findings == []


def test_scan_idle_cycles_non_active_dream_skipped():
    idle_cycles = [_FakeCycle(files_written=0) for _ in range(3)]
    dream = _FakeDream(cycles=idle_cycles, status="completed")
    store = _FakeDreamStore([dream])
    findings = scan_idle_cycles(store, window=3, atom_threshold=1)
    assert findings == []


def test_scan_idle_cycles_store_exception_returns_empty():
    class _BrokenStore:
        def list_all(self, **kwargs):
            raise RuntimeError("store failure")

    findings = scan_idle_cycles(_BrokenStore(), window=3, atom_threshold=1)
    assert findings == []


# ── scan_zombies ──────────────────────────────────────────────────────────────


def test_scan_zombies_no_findings_for_fresh_in_progress():
    cont = _FakeCont(status="in_progress", updated_at=_now_iso())
    store = _FakeContStore([cont])
    # threshold = 1 hour; our cont was updated just now → no zombie
    findings = scan_zombies(store, threshold_seconds=3600)
    assert findings == []


def test_scan_zombies_fires_ec_health_001_for_stale():
    cont = _FakeCont(
        status="in_progress",
        updated_at=_ago_iso(7200),  # 2 hours ago
    )
    store = _FakeContStore([cont])
    findings = scan_zombies(store, threshold_seconds=3600)
    # Should find a zombie
    assert len(findings) == 1
    assert findings[0].edge_case_id == "EC-HEALTH-001"
    assert findings[0].target == cont.task_id


def test_scan_zombies_skips_non_in_progress():
    cont = _FakeCont(status="done", updated_at=_ago_iso(7200))
    store = _FakeContStore([cont])
    findings = scan_zombies(store, threshold_seconds=3600)
    assert findings == []


def test_scan_zombies_store_exception_returns_empty():
    class _BrokenStore:
        def list_all(self, **kwargs):
            raise RuntimeError("store dead")

    findings = scan_zombies(_BrokenStore(), threshold_seconds=3600)
    assert findings == []


def test_scan_zombies_skips_cont_with_unparseable_timestamp():
    cont = _FakeCont(status="in_progress", updated_at="not-a-timestamp")
    store = _FakeContStore([cont])
    findings = scan_zombies(store, threshold_seconds=3600)
    assert findings == []


# ── plan_repairs ──────────────────────────────────────────────────────────────


def test_plan_repairs_zombie_gives_reset_to_planned():
    report = HealthReport(findings=[
        _finding(edge_case_id="EC-HEALTH-001", target="cont-zombie-001"),
    ])
    actions = plan_repairs(report)
    assert len(actions) == 1
    assert actions[0].kind == "reset_to_planned"
    assert actions[0].target == "cont-zombie-001"


def test_plan_repairs_idle_dream_gives_pause():
    report = HealthReport(findings=[
        _finding(edge_case_id="EC-DREAM-006", target="dream-idle-001"),
    ])
    actions = plan_repairs(report)
    assert len(actions) == 1
    assert actions[0].kind == "pause_idle_dream"
    assert actions[0].target == "dream-idle-001"


def test_plan_repairs_stale_lock_gives_remove_lock():
    report = HealthReport(findings=[
        _finding(
            edge_case_id="EC-CONT-002",
            target="cont-lock-001",
            details={"lock_path": "/tmp/fake.lock"},
        ),
    ])
    actions = plan_repairs(report)
    assert len(actions) == 1
    assert actions[0].kind == "remove_lock"


def test_plan_repairs_unknown_ec_produces_no_action():
    report = HealthReport(findings=[
        _finding(edge_case_id="EC-UNKNOWN-999"),
    ])
    actions = plan_repairs(report)
    assert actions == []


def test_plan_repairs_empty_report():
    report = HealthReport()
    assert plan_repairs(report) == []


# ── apply_repairs dry_run ─────────────────────────────────────────────────────


def test_apply_repairs_dry_run_does_not_apply():
    actions = [
        RepairAction(
            finding_id="cont-001",
            kind="reset_to_planned",
            target="cont-001",
            description="test",
        )
    ]
    result = apply_repairs(actions, dry_run=True)
    assert all(not a.applied for a in result)


def test_apply_repairs_dry_run_does_not_touch_files(tmp_path):
    lock_file = tmp_path / "test.lock"
    lock_file.write_text("12345")
    actions = [
        RepairAction(
            finding_id="test",
            kind="remove_lock",
            target=str(lock_file),
            description="remove lock",
        )
    ]
    apply_repairs(actions, dry_run=True)
    assert lock_file.exists(), "dry_run should not remove the lock file"
