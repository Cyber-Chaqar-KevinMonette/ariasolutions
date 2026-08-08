"""Tests for aria-timeout-ledger: real events.jsonl, real emit_event(),
real classification logic — no mocks on the read path."""
from __future__ import annotations

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


def test_no_timeouts_scans_as_justified_honestly(isolated_paths):
    from sovereign_agent.timeouts import record_timeout_scan

    result = record_timeout_scan(data_dir=isolated_paths)
    assert result.verdict == "justified"
    assert result.events == []


def test_a_catalogued_within_bound_timeout_is_justified(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts import record_timeout_scan

    emit_event("vram-lock-timeout-d", plane="control", trace_id="vram",
               payload={"tool": "aria_lm.grow_mind", "timeout_seconds": 60.0})

    result = record_timeout_scan(data_dir=isolated_paths)
    assert result.verdict == "justified"
    assert len(result.events) == 1
    assert result.events[0].verdict == "justified"
    assert result.events[0].catalogued_bound == 60.0


def test_a_catalogued_but_over_bound_timeout_is_unexplained(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts import record_timeout_scan

    emit_event("vram-lock-timeout-d", plane="control", trace_id="vram",
               payload={"tool": "aria_lm.grow_mind", "timeout_seconds": 300.0})

    result = record_timeout_scan(data_dir=isolated_paths)
    assert result.verdict == "unexplained"
    assert result.events[0].verdict == "unexplained"


def test_an_uncatalogued_timeout_source_is_unexplained(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts import record_timeout_scan

    emit_event("some-new-subsystem-timeout-d", plane="control", trace_id="x",
               payload={"tool": "brand_new_thing", "timeout_seconds": 5.0})

    result = record_timeout_scan(data_dir=isolated_paths)
    assert result.verdict == "unexplained"
    assert result.events[0].catalogued_bound is None


def test_the_scans_own_summary_event_is_never_recursively_classified(isolated_paths):
    """The real bug this design caught: emit_event("timeout-scan-d", ...)
    contains the substring "timeout" but must never be picked up by the
    NEXT scan as an unexplained timeout occurrence."""
    from sovereign_agent.timeouts import record_timeout_scan

    record_timeout_scan(data_dir=isolated_paths)  # emits its own timeout-scan-d event
    second = record_timeout_scan(data_dir=isolated_paths)
    assert second.events == []
    assert second.verdict == "justified"


def test_scan_persists_and_round_trips(isolated_paths):
    from sovereign_agent.events import emit_event
    from sovereign_agent.timeouts import latest_timeout_scan, record_timeout_scan

    emit_event("vram-lock-timeout-d", plane="control", trace_id="vram",
               payload={"tool": "aria_lm.grow_mind", "timeout_seconds": 60.0})
    result = record_timeout_scan(data_dir=isolated_paths)
    latest = latest_timeout_scan(isolated_paths)
    assert latest is not None
    assert latest["scan_id"] == result.scan_id


def test_trend_reports_insufficient_history_honestly(isolated_paths):
    from sovereign_agent.timeouts import record_timeout_scan, timeout_trend

    assert timeout_trend(data_dir=isolated_paths) == "insufficient-history"
    record_timeout_scan(data_dir=isolated_paths)
    assert timeout_trend(data_dir=isolated_paths) == "insufficient-history"
