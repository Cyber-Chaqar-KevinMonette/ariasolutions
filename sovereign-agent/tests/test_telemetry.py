"""Tests for cockpit/telemetry.py and sov telemetry CLI — v0.2.15.3."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def test_telemetry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib
    import sovereign_agent.cockpit.telemetry as t
    importlib.reload(t)
    from sovereign_agent.cockpit.sysmon import SystemMonitor

    m = SystemMonitor()
    s = m.read()
    p = t.write_sample(s, vram_total_mb=8192, vram_used_mb=2048, vram_temp_c=68.0)
    assert p is not None
    assert p.exists()
    # The file is JSONL
    line = p.read_text(encoding="utf-8").splitlines()[0]
    rec = json.loads(line)
    assert "ts" in rec
    assert "ram_pct" in rec
    assert "vram_pct" in rec
    assert rec["vram_temp_c"] == 68.0


def test_telemetry_extra_dict_merges(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib
    import sovereign_agent.cockpit.telemetry as t
    importlib.reload(t)
    from sovereign_agent.cockpit.sysmon import SystemMonitor

    s = SystemMonitor().read()
    t.write_sample(s, extra={
        "task_directive": "inventory ~/AA-Erebo",
        "task_phase": "end",
        "task_duration_s": 4.2,
    })
    rows = t.tail_today(10)
    assert len(rows) == 1
    assert rows[0]["task_directive"] == "inventory ~/AA-Erebo"
    assert rows[0]["task_phase"] == "end"
    assert rows[0]["task_duration_s"] == 4.2


def test_telemetry_tail_returns_empty_for_fresh_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib
    import sovereign_agent.cockpit.telemetry as t
    importlib.reload(t)
    assert t.tail_today(10) == []


def test_telemetry_write_does_not_raise(tmp_path, monkeypatch):
    """write_sample must NEVER raise — telemetry can't break the cockpit."""
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib
    import sovereign_agent.cockpit.telemetry as t
    importlib.reload(t)
    from sovereign_agent.cockpit.sysmon import SystemMonitor

    # Inject a failure: patch open() to always raise
    def _bad_open(*a, **kw):
        raise OSError("disk full (simulated)")
    monkeypatch.setattr("builtins.open", _bad_open)

    s = SystemMonitor().read()
    # If this raises, the test fails. The return value can be None or
    # whatever — the contract is "no exception escapes write_sample".
    t.write_sample(s)     # must not raise


def test_telemetry_summarise_with_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib
    import sovereign_agent.cockpit.telemetry as t
    importlib.reload(t)
    from sovereign_agent.cockpit.sysmon import SystemMonitor

    s = SystemMonitor().read()
    for _ in range(5):
        t.write_sample(s, vram_total_mb=8192, vram_used_mb=2048)
    out = t.summarise(days=1)
    assert out["sample_count"] == 5
    assert "cpu_pct" in out
    assert out["cpu_pct"]["n"] == 5
    assert "vram_pct" in out
    assert out["vram_pct"]["n"] == 5


def test_telemetry_record_drops_none_fields(tmp_path, monkeypatch):
    """If cpu_temp_c is None (e.g., container), it should NOT land in the
    JSONL record. Avoids null columns in historical files."""
    monkeypatch.setenv("AGENT_DATA", str(tmp_path / "data"))
    import importlib
    import sovereign_agent.cockpit.telemetry as t
    importlib.reload(t)
    from sovereign_agent.cockpit.sysmon import SystemSnapshot

    s = SystemSnapshot(
        cpu_percent=12.0, cpu_temp_c=None,
        mem_total=1, mem_used=0, mem_percent=10.0,
        disk_total=1, disk_used=0, disk_percent=20.0,
    )
    rec = t.snapshot_to_record(s)
    assert "cpu_temp_c" not in rec      # None → dropped
    assert "vram_pct" not in rec        # not supplied → dropped
    assert "cpu_pct" in rec             # always present


# ── render_compact_metrics with temperatures ────────────────────────────────


def test_compact_metrics_appends_cpu_temp():
    from sovereign_agent.cockpit.sysmon import (
        SystemSnapshot, render_compact_metrics,
    )
    s = SystemSnapshot(cpu_percent=10.0, cpu_temp_c=62.0,
                       mem_total=1, mem_percent=20.0,
                       disk_total=1, disk_percent=30.0)
    out = render_compact_metrics(s)
    assert "62°" in out
    assert "@" in out


def test_compact_metrics_appends_vram_temp_when_supplied():
    from sovereign_agent.cockpit.sysmon import (
        SystemSnapshot, render_compact_metrics,
    )
    s = SystemSnapshot(cpu_percent=10.0, mem_total=1, mem_percent=20.0,
                       disk_total=1, disk_percent=30.0)
    out = render_compact_metrics(s, vram_percent=42.0, vram_temp_c=72.0)
    assert "72°" in out
    assert "vram" in out
    assert "[yellow]72°" in out         # 70-84°C → yellow


def test_compact_metrics_no_temp_when_unavailable():
    from sovereign_agent.cockpit.sysmon import (
        SystemSnapshot, render_compact_metrics,
    )
    s = SystemSnapshot(cpu_percent=10.0, cpu_temp_c=None,
                       mem_total=1, mem_percent=20.0,
                       disk_total=1, disk_percent=30.0)
    out = render_compact_metrics(s)
    # No "@N°" suffix anywhere
    assert "@" not in out
    assert "°" not in out
