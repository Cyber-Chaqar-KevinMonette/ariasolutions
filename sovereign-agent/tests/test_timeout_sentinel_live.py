"""Tests for aria-timeout-sentinel: real events.jsonl, real Sentinel
machinery, controlled input via emit_event fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir.parent))
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()
    original = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield data_dir
    finally:
        object.__setattr__(SETTINGS, "paths", original)


def test_scan_with_no_timeouts_reports_ok(isolated_paths):
    from sovereign_agent.stewardship.timeout_sentinel import TimeoutSentinel

    sentinel = TimeoutSentinel(isolated_paths)
    report = sentinel.scan()
    assert report.findings_count == 0
    assert "nothing to score" in report.summary


def test_scan_finds_an_unexplained_timeout(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.stewardship.timeout_sentinel import TimeoutSentinel

    emit_event("some-new-subsystem-timeout-d", plane="control", trace_id="x",
              payload={"tool": "brand_new_thing", "timeout_seconds": 5.0})

    sentinel = TimeoutSentinel(isolated_paths)
    report = sentinel.scan()
    assert report.findings_count == 1
    health = sentinel.health_status()
    assert health.level == "warning"


def test_a_justified_timeout_reports_clean(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.stewardship.timeout_sentinel import TimeoutSentinel

    emit_event("vram-lock-timeout-d", plane="control", trace_id="vram",
              payload={"tool": "aria_lm.grow_mind", "timeout_seconds": 60.0})

    sentinel = TimeoutSentinel(isolated_paths)
    report = sentinel.scan()
    assert report.findings_count == 0
    health = sentinel.health_status()
    assert health.level == "ok"


def test_second_scan_does_not_rereport_the_same_unexplained_timeout(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.stewardship.timeout_sentinel import TimeoutSentinel

    emit_event("some-new-subsystem-timeout-d", plane="control", trace_id="x",
              payload={"tool": "brand_new_thing", "timeout_seconds": 5.0})

    sentinel = TimeoutSentinel(isolated_paths)
    first = sentinel.scan()
    assert first.findings_count == 1

    second = sentinel.scan()
    assert second.findings_count == 0  # already reported, not newly-appeared


def test_proposals_names_the_remediation(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.stewardship.timeout_sentinel import TimeoutSentinel

    emit_event("some-new-subsystem-timeout-d", plane="control", trace_id="x",
              payload={"tool": "brand_new_thing", "timeout_seconds": 5.0})

    sentinel = TimeoutSentinel(isolated_paths)
    report = sentinel.scan()
    proposals = sentinel.proposals(report)
    assert len(proposals) >= 1
    assert "TIMEOUT_CATALOG" in proposals[0]["remediation"]
