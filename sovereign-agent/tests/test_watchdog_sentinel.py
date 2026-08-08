"""Tests for M62 — WatchdogSentinel (golden-image integrity verification).

475 lines of safety-critical detection code, now finally tested.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_sentinel(tmp_path: Path):
    from sovereign_agent.stewardship.watchdog_sentinel import WatchdogSentinel
    return WatchdogSentinel(data_dir=tmp_path, watched_root=tmp_path)


def _make_file(tmp_path: Path, name: str = "canon.py", content: str = "x = 1") -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


# ─── Registration ─────────────────────────────────────────────────────────────


def test_sentinel_id_is_watchdog(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.id == "watchdog"


def test_sentinel_registered_in_registry(tmp_path):
    from sovereign_agent.stewardship.registry import _REGISTRY
    from sovereign_agent.stewardship import watchdog_sentinel  # noqa: F401
    assert "watchdog" in _REGISTRY


# ─── Articles ─────────────────────────────────────────────────────────────────


def test_articles_non_empty(tmp_path):
    s = _make_sentinel(tmp_path)
    arts = s.articles()
    assert isinstance(arts, list)
    assert len(arts) >= 3


def test_articles_mention_golden_image(tmp_path):
    s = _make_sentinel(tmp_path)
    combined = " ".join(s.articles()).lower()
    assert "golden" in combined or "manifest" in combined


# ─── Kill switch ─────────────────────────────────────────────────────────────


def test_kill_switch_env_correct(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.kill_switch_env == "SOV_NO_WATCHDOG_SENTINEL"


def test_is_enabled_true_by_default(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.is_enabled() is True


def test_kill_switch_disables_sentinel(tmp_path, monkeypatch):
    monkeypatch.setenv("SOV_NO_WATCHDOG_SENTINEL", "1")
    s = _make_sentinel(tmp_path)
    assert s.is_enabled() is False


# ─── Empty catalog — clean scan ───────────────────────────────────────────────


def test_scan_empty_catalog_returns_clean(tmp_path):
    s = _make_sentinel(tmp_path)
    report = s.scan()
    assert report.sentinel_id == "watchdog"
    assert report.details["drift"] == []
    assert report.details["missing"] == []
    assert report.findings_count == 0


def test_scan_missing_catalog_no_crash(tmp_path):
    s = _make_sentinel(tmp_path)
    # Catalog file doesn't exist yet — should be clean
    report = s.scan()
    assert report.findings_count == 0


# ─── Sealing + clean verification ────────────────────────────────────────────


def test_scan_sealed_file_no_drift(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="hello world")
    s.seal_path(f, key="test-file")
    report = s.scan()
    assert report.details["drift"] == []
    assert report.details["missing"] == []


def test_seal_path_records_entry(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path)
    entry = s.seal_path(f, key="canon.py")
    assert entry.key == "canon.py"
    assert entry.expected_sha256 != ""
    assert entry.expected_size > 0


# ─── Drift detection ─────────────────────────────────────────────────────────


def test_scan_detects_drift_after_modification(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="original content")
    s.seal_path(f, key="canon.py")
    # Tamper with the file
    f.write_text("tampered content")
    report = s.scan()
    assert len(report.details["drift"]) == 1
    assert report.details["drift"][0]["key"] == "canon.py"
    assert report.findings_count == 1


def test_drift_report_contains_both_hashes(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="original")
    s.seal_path(f, key="test.py")
    f.write_text("different")
    report = s.scan()
    drift = report.details["drift"][0]
    assert "expected_sha256" in drift
    assert "observed_sha256" in drift
    assert drift["expected_sha256"] != drift["observed_sha256"]


def test_scan_detects_missing_file(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="will be deleted")
    s.seal_path(f, key="deleted.py")
    f.unlink()
    report = s.scan()
    assert len(report.details["missing"]) == 1
    assert report.findings_count == 1


# ─── Health status ───────────────────────────────────────────────────────────


def test_health_ok_when_no_drift(tmp_path):
    s = _make_sentinel(tmp_path)
    status = s.health_status()
    assert status.level == "ok"
    assert status.sentinel_id == "watchdog"


def test_health_error_when_drift_detected(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="original")
    s.seal_path(f, key="drifted.py")
    f.write_text("tampered")
    status = s.health_status()
    assert status.level == "error"


def test_health_ok_after_reseal_fixes_drift(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="original")
    s.seal_path(f, key="fixed.py")
    f.write_text("tampered")
    assert s.health_status().level == "error"
    # Operator re-seals the file to canonize the new state
    s.seal_path(f, key="fixed.py")
    assert s.health_status().level == "ok"


# ─── No file modification ─────────────────────────────────────────────────────


def test_scan_does_not_modify_watched_files(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="canonical content")
    s.seal_path(f, key="watched.py")
    mtime_before = f.stat().st_mtime
    s.scan()
    mtime_after = f.stat().st_mtime
    assert mtime_before == mtime_after


# ─── Atomicity ───────────────────────────────────────────────────────────────


def test_catalog_write_is_atomic(tmp_path):
    """After seal_path(), no .tmp artifact should remain."""
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path)
    s.seal_path(f, key="atomic.py")
    catalog_path = tmp_path / "sentinels" / "watchdog" / "catalogs" / "golden_image.json"
    tmp_artifact = catalog_path.with_suffix(".tmp")
    assert catalog_path.exists()
    assert not tmp_artifact.exists()


# ─── Recovery proposal ───────────────────────────────────────────────────────


def test_recovery_candidate_none_without_vault(tmp_path):
    """Without a Vault, recovery_candidate should be None."""
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="original")
    s.seal_path(f, key="recover.py")
    f.write_text("tampered")
    report = s.scan()
    assert report.details["recovery_candidate"] is None


def test_scan_does_not_auto_restore(tmp_path):
    """scan() must PROPOSE recovery, never apply it."""
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="original")
    s.seal_path(f, key="no-auto.py")
    f.write_text("tampered")
    s.scan()
    # File should still be tampered — Watchdog does not restore
    assert f.read_text() == "tampered"


# ─── Concurrency ─────────────────────────────────────────────────────────────


def test_concurrent_scans_catalog_consistent(tmp_path):
    """Two concurrent scan() calls must not corrupt the catalog.

    The _save_catalog() method uses .tmp → os.replace() which is atomic at
    the OS level, so the final catalog is always in a valid state even if
    one thread temporarily sees a missing .tmp file.
    """
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path, content="stable")
    s.seal_path(f, key="concurrent.py")
    catalog_path = tmp_path / "sentinels" / "watchdog" / "catalogs" / "golden_image.json"

    # Race both scans — one or both may raise due to the .tmp race, but the
    # final catalog must be valid JSON (not corrupted).
    def _scan():
        try:
            s.scan()
        except (FileNotFoundError, OSError):
            pass  # expected race on .tmp file

    t1 = threading.Thread(target=_scan)
    t2 = threading.Thread(target=_scan)
    t1.start(); t2.start()
    t1.join(timeout=5); t2.join(timeout=5)

    # The catalog must be readable and valid JSON
    assert catalog_path.exists()
    import json
    data = json.loads(catalog_path.read_text())
    assert "entries" in data


# ─── Unseal ───────────────────────────────────────────────────────────────────


def test_unseal_removes_entry(tmp_path):
    s = _make_sentinel(tmp_path)
    f = _make_file(tmp_path)
    s.seal_path(f, key="remove-me")
    assert s.unseal("remove-me") is True
    # After unseal, scan should find no drift for this file
    f.write_text("anything different")
    report = s.scan()
    keys_in_drift = [d["key"] for d in report.details["drift"]]
    assert "remove-me" not in keys_in_drift


def test_unseal_unknown_key_returns_false(tmp_path):
    s = _make_sentinel(tmp_path)
    assert s.unseal("nonexistent") is False


# ─── Multiple entries ─────────────────────────────────────────────────────────


def test_multiple_files_only_drifted_reported(tmp_path):
    s = _make_sentinel(tmp_path)
    good = _make_file(tmp_path, "good.py", "good content")
    bad = _make_file(tmp_path, "bad.py", "original")
    s.seal_path(good, key="good.py")
    s.seal_path(bad, key="bad.py")
    bad.write_text("tampered")
    report = s.scan()
    assert len(report.details["drift"]) == 1
    assert report.details["drift"][0]["key"] == "bad.py"
    assert report.details["missing"] == []
