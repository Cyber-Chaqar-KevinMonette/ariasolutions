"""
test_sysmon.py — unit tests for the cockpit's system monitor and report
renderers. These do not need a running daemon.
"""
from __future__ import annotations

import time

import pytest

from sovereign_agent.cockpit.sysmon import (
    SystemMonitor,
    SystemSnapshot,
    fmt_bytes,
    fmt_duration,
    render_compact_metrics,
    render_health_report,
)


# ── Pure formatters ─────────────────────────────────────────────────────────


def test_fmt_bytes_thresholds():
    assert fmt_bytes(0) == "0 B"
    assert fmt_bytes(42) == "42 B"
    assert fmt_bytes(1023) == "1023 B"
    assert fmt_bytes(1024) == "1.00 KB"
    assert fmt_bytes(1500).endswith(" KB")
    assert fmt_bytes(1_500_000).endswith(" MB")
    assert fmt_bytes(1_500_000_000).endswith(" GB")


def test_fmt_duration_thresholds():
    assert fmt_duration(3) == "3s"
    assert fmt_duration(75) == "1m 15s"
    assert fmt_duration(3700) == "1h 1m"
    assert fmt_duration(90000) == "1d 1h"


# ── SystemMonitor reads ──────────────────────────────────────────────────────


def test_monitor_first_read_does_not_raise():
    """First read seeds the CPU baseline — cpu_percent must be 0.0 not NaN."""
    m = SystemMonitor()
    s = m.read()
    assert isinstance(s, SystemSnapshot)
    assert s.error == ""
    assert s.cpu_percent == 0.0      # no prior sample yet
    assert s.cpu_count >= 1
    assert s.mem_total > 0           # any Linux box has memory
    assert s.mem_percent >= 0.0
    assert s.disk_total > 0


def test_monitor_second_read_gives_real_cpu():
    """After a brief sleep, second read should produce a real diff."""
    m = SystemMonitor()
    m.read()
    time.sleep(0.15)
    s = m.read()
    assert 0.0 <= s.cpu_percent <= 100.0


def test_monitor_uptime_is_positive():
    s = SystemMonitor().read()
    assert s.uptime_seconds > 0


# ── Renderers ───────────────────────────────────────────────────────────────


def test_compact_metrics_has_three_components():
    s = SystemMonitor().read()
    out = render_compact_metrics(s)
    assert "ram" in out
    assert "cpu" in out
    assert "disk" in out
    assert "vram" not in out          # not provided → omitted


def test_compact_metrics_includes_vram_when_supplied():
    s = SystemMonitor().read()
    out = render_compact_metrics(s, vram_percent=42.0)
    assert "vram" in out
    assert "42%" in out


def test_compact_metrics_colour_thresholds():
    """A 50% value should be green, 70% yellow, 90% red."""
    s = SystemSnapshot(
        mem_percent=50.0, cpu_percent=70.0, disk_percent=90.0,
        mem_total=1, disk_total=1,
    )
    out = render_compact_metrics(s)
    assert "[green]50%" in out
    assert "[yellow]70%" in out
    assert "[red]90%" in out


def test_full_report_contains_all_sections():
    s = SystemMonitor().read()
    r = render_health_report(
        s,
        version="0.2.15.3",
        halt=False,
        daemon_active=True,
        ledger_ok=True,
        ledger_rows=42,
        snapshot_age_seconds=3600,
        snapshot_verify_ok=True,
        now_iso="2026-05-11 14:23 UTC",
    )
    assert "sovereign-agent · health report" in r
    assert "Version" in r
    assert "Uptime" in r
    assert "Daemon" in r
    assert "HALT" in r
    assert "System" in r
    assert "CPU" in r
    assert "Memory" in r
    assert "Disk" in r
    assert "Ledger" in r
    assert "Backups" in r
    assert "42" in r            # ledger_rows is rendered
    assert "0.2.15.3" in r


def test_full_report_with_vram():
    s = SystemMonitor().read()
    r = render_health_report(
        s, version="0.2.15.3",
        halt=False, daemon_active=True,
        ledger_ok=True, ledger_rows=0,
        snapshot_age_seconds=None, snapshot_verify_ok=True,
        vram_total_mb=8192, vram_used_mb=2100, vram_source="nvidia-smi",
        now_iso="2026-05-11 14:23 UTC",
    )
    assert "VRAM" in r
    assert "8192" in r
    assert "nvidia-smi" in r


def test_full_report_when_halted_says_so():
    s = SystemMonitor().read()
    r = render_health_report(
        s, version="0.2.15.3",
        halt=True, daemon_active=False,
        ledger_ok=False, ledger_rows=0,
        snapshot_age_seconds=None, snapshot_verify_ok=False,
        now_iso="t",
    )
    assert "TRIPPED" in r
    assert "inactive" in r
    assert "discrepancy" in r
    assert "(no snapshot)" in r


# ── Cockpit integration ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_slash_command_writes_to_chat():
    """`/health` must print at least the daemon line and the cpu/mem/disk lines."""
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Force a status read so .system is populated.
        app.status = await app._async_read_status() if hasattr(app, "_async_read_status") else app.status
        s = app._read_status()
        app.status = s
        await pilot.pause()

        chat = app.query_one("#chat-log")
        before = len(chat.lines)
        msg = Input.Submitted(app.query_one("#input-box"), "/health", validation_result=None)
        app.on_input_submitted(msg)
        await pilot.pause()
        after = len(chat.lines)
        # /health writes at least 5 lines (header + 4 metric lines).
        assert after - before >= 5


@pytest.mark.asyncio
async def test_report_slash_command_writes_a_file(tmp_path, monkeypatch):
    """`/report` saves a timestamped report under data_dir/reports/."""
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Input

    # Redirect data_dir to a tmp path so we don't pollute real data.
    monkeypatch.setattr(
        "sovereign_agent.cockpit.app.CockpitApp._resolve_data_dir",
        staticmethod(lambda: tmp_path),
    )

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Seed status.
        app.status = app._read_status()
        await pilot.pause()

        msg = Input.Submitted(app.query_one("#input-box"), "/report", validation_result=None)
        app.on_input_submitted(msg)
        await pilot.pause()

        reports_dir = tmp_path / "reports"
        assert reports_dir.exists()
        reports = list(reports_dir.glob("health-*.txt"))
        assert len(reports) == 1
        text = reports[0].read_text()
        assert "sovereign-agent · health report" in text
        assert "System" in text
