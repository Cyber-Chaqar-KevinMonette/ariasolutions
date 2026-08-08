"""Tests for the cache sentinel — the agent that catches uv-skip-rebuild bugs."""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sovereign_agent.stewardship.cache_sentinel import CacheSentinel


def test_cache_sentinel_has_correct_identity(tmp_path):
    s = CacheSentinel(tmp_path)
    assert s.id == "cache"
    assert s.tier == 1
    assert len(s.articles()) >= 5  # multiple binding statements


def test_cache_sentinel_articles_include_the_lesson(tmp_path):
    """The sentinel's first article should be about the actual bug we hit."""
    s = CacheSentinel(tmp_path)
    articles = s.articles()
    # First article should be about source-vs-installed detection
    assert any("source" in a.lower() and "installed" in a.lower() for a in articles), \
        f"sentinel should remember its origin bug; articles={articles}"


def test_cache_sentinel_bootstrap_seals_manifest(tmp_path):
    s = CacheSentinel(tmp_path)
    m = s.bootstrap()
    assert m.verify_hash()
    assert m.id == "cache"
    assert m.kill_switch_env == "SOV_NO_CACHE_SENTINEL"


def test_cache_sentinel_scan_produces_catalog(tmp_path):
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    report = s.scan()
    assert report.sentinel_id == "cache"
    assert report.catalog_path
    # Catalog should exist on disk
    assert s.load_catalog("default") is not None


def test_cache_sentinel_health_reports_unknown_before_first_scan(tmp_path):
    s = CacheSentinel(tmp_path)
    health = s.health_status()
    assert health.level == "unknown"
    assert "never scanned" in health.summary


def test_cache_sentinel_health_reports_ok_after_clean_scan(tmp_path):
    """When the source matches the installed package, health is ok."""
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    s.scan()
    health = s.health_status()
    # In test environment, source and installed should match (both running same code)
    # so we expect ok or warning at worst (lockfile age may differ)
    assert health.level in ("ok", "warning", "info")


def test_version_drift_detection_when_mocked(tmp_path):
    """If pyproject says one version and metadata says another, alert fires."""
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    # Mock all three version sources to be different
    with patch.object(s, "_version_from_pyproject", return_value="9.9.9"), \
         patch.object(s, "_version_from_init",     return_value="1.0.0"), \
         patch.object(s, "_version_from_metadata", return_value="0.0.1"):
        findings = s._check_version_drift()
    assert len(findings) == 1
    assert findings[0].kind == "version-drift"
    assert findings[0].severity == "alert"


def test_version_drift_silent_when_aligned(tmp_path):
    s = CacheSentinel(tmp_path)
    with patch.object(s, "_version_from_pyproject", return_value="0.2.34.0"), \
         patch.object(s, "_version_from_init",     return_value="0.2.34.0"), \
         patch.object(s, "_version_from_metadata", return_value="0.2.34.0"):
        findings = s._check_version_drift()
    assert findings == []


def test_source_vs_installed_detects_missing_module(tmp_path, monkeypatch):
    """The bug Kevin caught: a source module that's not importable from the installed package."""
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    # Mock the source path discovery to point at a synthetic tree containing
    # a module that definitely isn't in the installed sovereign_agent package
    fake_src = tmp_path / "src" / "sovereign_agent"
    fake_src.mkdir(parents=True)
    (fake_src / "__init__.py").write_text("__version__ = '0.0.0'\n")
    (fake_src / "ghost_module_never_installed_zzzz.py").write_text("# nope\n")
    with patch.object(s, "_find_source_path", return_value=fake_src):
        findings = s._check_source_vs_installed()
    # Should flag ghost_module as source-vs-venv alert
    assert any(f.kind == "source-vs-venv" for f in findings)
    drift = next(f for f in findings if f.kind == "source-vs-venv")
    assert drift.severity == "alert"
    assert "ghost_module" in drift.detail


def test_stale_lockfile_detection(tmp_path):
    """uv.lock older than pyproject.toml → warning."""
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    fake_root = tmp_path / "fake-project"
    fake_src = fake_root / "src" / "sovereign_agent"
    fake_src.mkdir(parents=True)
    (fake_src / "__init__.py").write_text("")
    pyproject = fake_root / "pyproject.toml"
    lockfile = fake_root / "uv.lock"
    # Create lockfile first, then pyproject — pyproject newer
    lockfile.write_text("# old lock\n")
    time.sleep(1.1)  # ensure mtime resolution
    pyproject.write_text("[project]\nversion = \"1.0.0\"\n")
    with patch.object(s, "_find_source_path", return_value=fake_src):
        findings = s._check_lockfile_age()
    assert len(findings) == 1
    assert findings[0].kind == "stale-lockfile"
    assert findings[0].severity == "warning"


def test_alert_findings_emit_notifications(tmp_path):
    """When the scan finds an alert, the inbox should have a notification."""
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    # Mock to force an alert
    with patch.object(s, "_version_from_pyproject", return_value="9.9.9"), \
         patch.object(s, "_version_from_init",     return_value="1.0.0"), \
         patch.object(s, "_version_from_metadata", return_value="0.0.1"):
        s.scan()
    unread = s.read_inbox(only_unread=True)
    assert len(unread) >= 1
    assert any(n.severity == "alert" for n in unread)


def test_kill_switch_does_not_break_health(tmp_path):
    """Health can still be queried when the sentinel is disabled."""
    s = CacheSentinel(tmp_path)
    s.bootstrap()
    with patch.dict(os.environ, {s.kill_switch_env: "1"}):
        # health_status itself works (just reports unknown if never scanned)
        h = s.health_status()
        assert h.level in ("ok", "warning", "error", "unknown")
        assert not s.is_enabled()
