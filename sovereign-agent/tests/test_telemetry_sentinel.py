"""
test_telemetry_sentinel.py — Tests for TelemetrySentinel (M27).
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone


def _make_sample(**kwargs) -> dict:
    """Create a minimal telemetry sample with sensible defaults."""
    base = {
        "ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "cpu_pct": 10.0,
        "ram_pct": 40.0,
        "disk_free_mb": 50_000,
        "disk_total_mb": 100_000,
        "disk_pct": 50.0,
    }
    base.update(kwargs)
    return base


def _write_telemetry(data_dir: Path, samples: list[dict]) -> None:
    tdir = data_dir / "telemetry"
    tdir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    path = tdir / f"sys-{today}.jsonl"
    with path.open("w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")


# ── _analyze_samples tests ────────────────────────────────────────────────

def test_analyze_samples_healthy():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    samples = [_make_sample() for _ in range(15)]
    result = _analyze_samples(samples)
    assert result["level"] == "ok"
    assert result["findings"] == []


def test_analyze_samples_disk_error():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    samples = [_make_sample(disk_free_mb=500) for _ in range(5)]  # < 1 GB
    result = _analyze_samples(samples)
    assert result["level"] == "error"
    assert any("disk critically" in f for f in result["findings"])


def test_analyze_samples_disk_warning():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    samples = [_make_sample(disk_free_mb=3000) for _ in range(5)]  # 3 GB, < 5 GB
    result = _analyze_samples(samples)
    assert result["level"] == "warning"
    assert any("disk low" in f for f in result["findings"])


def test_analyze_samples_gpu_temp_error():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    samples = [_make_sample(vram_temp_c=90.0) for _ in range(5)]
    result = _analyze_samples(samples)
    assert result["level"] == "error"
    assert any("critical" in f for f in result["findings"])


def test_analyze_samples_gpu_temp_warning():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    samples = [_make_sample(vram_temp_c=82.0) for _ in range(5)]
    result = _analyze_samples(samples)
    assert result["level"] == "warning"
    assert any("GPU temp high" in f for f in result["findings"])


def test_analyze_samples_vram_error():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples, VRAM_WARN_SAMPLES
    samples = [_make_sample(vram_pct=96.0) for _ in range(VRAM_WARN_SAMPLES)]
    result = _analyze_samples(samples)
    assert result["level"] == "error"
    assert any("VRAM critical" in f for f in result["findings"])


def test_analyze_samples_vram_warning():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples, VRAM_WARN_SAMPLES
    samples = [_make_sample(vram_pct=92.0) for _ in range(VRAM_WARN_SAMPLES)]
    result = _analyze_samples(samples)
    assert result["level"] == "warning"
    assert any("VRAM high" in f for f in result["findings"])


def test_analyze_samples_cpu_sustained_warning():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples, CPU_WARN_SAMPLES
    samples = [_make_sample(cpu_pct=95.0) for _ in range(CPU_WARN_SAMPLES)]
    result = _analyze_samples(samples)
    assert result["level"] == "warning"
    assert any("CPU sustained" in f for f in result["findings"])


def test_analyze_samples_empty_returns_unknown():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    result = _analyze_samples([])
    assert result["level"] == "unknown"


def test_analyze_samples_cpu_not_sustained_ok():
    from sovereign_agent.stewardship.telemetry_sentinel import _analyze_samples
    # Only a few high CPU samples — not sustained
    samples = [_make_sample(cpu_pct=95.0)] * 3 + [_make_sample(cpu_pct=20.0)] * 10
    result = _analyze_samples(samples)
    # Should not trigger warning — not enough sustained samples
    assert "CPU sustained" not in " ".join(result["findings"])


# ── TelemetrySentinel integration tests ──────────────────────────────────

def test_sentinel_registered():
    import sovereign_agent.stewardship  # noqa: F401
    from sovereign_agent.stewardship.registry import registered_ids
    assert "telemetry" in registered_ids()


def test_sentinel_articles_count():
    from sovereign_agent.stewardship.telemetry_sentinel import TelemetrySentinel
    from unittest.mock import MagicMock
    s = TelemetrySentinel.__new__(TelemetrySentinel)
    s._data_dir = Path("/tmp")
    assert len(s.articles()) >= 6


def test_sentinel_health_status_unknown_before_scan(tmp_path):
    from sovereign_agent.stewardship.telemetry_sentinel import TelemetrySentinel
    s = TelemetrySentinel(tmp_path)
    hs = s.health_status()
    assert hs.level == "unknown"
    assert "not yet scanned" in hs.summary


def test_sentinel_scan_healthy(tmp_path):
    from sovereign_agent.stewardship.telemetry_sentinel import TelemetrySentinel
    _write_telemetry(tmp_path, [_make_sample() for _ in range(20)])
    s = TelemetrySentinel(tmp_path)
    report = s.scan()
    assert report.sentinel_id == "telemetry"

    hs = s.health_status()
    assert hs.level == "ok"


def test_sentinel_scan_disk_error(tmp_path):
    from sovereign_agent.stewardship.telemetry_sentinel import TelemetrySentinel
    _write_telemetry(tmp_path, [_make_sample(disk_free_mb=500) for _ in range(5)])
    s = TelemetrySentinel(tmp_path)
    s.scan()
    hs = s.health_status()
    assert hs.level == "error"
    assert "disk" in hs.summary.lower()


def test_sentinel_kill_switch(tmp_path, monkeypatch):
    from sovereign_agent.stewardship.telemetry_sentinel import TelemetrySentinel
    monkeypatch.setenv("SOV_NO_TELEMETRY_SENTINEL", "1")
    s = TelemetrySentinel(tmp_path)
    assert not s.is_enabled()
