"""Tests for the unified sentinel framework (stewardship/base.py + registry.py)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from sovereign_agent.stewardship import base as _base
from sovereign_agent.stewardship import registry as _reg


class _ToySentinel(_base.Sentinel):
    """Minimal sentinel for framework tests. Reports static health."""

    @property
    def id(self) -> str:
        return "toy"

    @property
    def title(self) -> str:
        return "Toy sentinel for tests"

    def articles(self) -> list[str]:
        return ["I am a toy.", "I do toy things.", "I never break the world."]

    def scan(self) -> _base.SentinelReport:
        from sovereign_agent.stewardship.base import _iso_now
        catalog = {"scanned_at": _iso_now(), "counts": {"alert": 0, "warning": 0, "info": 1},
                   "findings": [{"kind": "test", "severity": "info", "summary": "toy"}]}
        path = self.save_catalog(catalog)
        return _base.SentinelReport(
            sentinel_id=self.id, observed_at=_iso_now(),
            catalog_name="default", findings_count=1,
            summary="1 info", catalog_path=str(path),
        )

    def health_status(self) -> _base.HealthStatus:
        return _base.HealthStatus(
            sentinel_id=self.id, level="ok", summary="toy is fine",
        )


# ─── Manifest hash + integrity ────────────────────────────────────────────


def test_manifest_seal_then_verify_passes():
    m = _base.SentinelManifest(id="x", title="X", articles=["a", "b"])
    m.seal()
    assert m.verify_hash()


def test_manifest_tamper_fails_verification():
    m = _base.SentinelManifest(id="x", title="X", articles=["a", "b"])
    m.seal()
    m.articles.append("inserted")  # tamper
    assert not m.verify_hash()


# ─── Bootstrap + persistence ─────────────────────────────────────────────


def test_bootstrap_creates_and_seals_manifest(tmp_path):
    s = _ToySentinel(tmp_path)
    m = s.bootstrap()
    assert m.manifest_hash
    assert m.verify_hash()
    assert s.manifest_path.is_file()


def test_bootstrap_is_idempotent(tmp_path):
    s = _ToySentinel(tmp_path)
    m1 = s.bootstrap()
    m2 = s.bootstrap()
    assert m1.manifest_hash == m2.manifest_hash


def test_bootstrap_reseals_when_articles_evolve(tmp_path):
    """If a code change adds an article, the manifest re-seals on next bootstrap."""
    s = _ToySentinel(tmp_path)
    m1 = s.bootstrap()
    # Simulate a new article in source code
    original_articles = _ToySentinel.articles
    try:
        _ToySentinel.articles = lambda self: original_articles(self) + ["new article"]
        s2 = _ToySentinel(tmp_path)
        m2 = s2.bootstrap()
        assert "new article" in m2.articles
        assert m2.verify_hash()
        assert m2.manifest_hash != m1.manifest_hash
    finally:
        _ToySentinel.articles = original_articles


# ─── Kill switches ───────────────────────────────────────────────────────


def test_per_sentinel_kill_switch(tmp_path):
    s = _ToySentinel(tmp_path)
    assert s.is_enabled()
    with patch.dict(os.environ, {s.kill_switch_env: "1"}):
        assert not s.is_enabled()


def test_master_kill_switch_disables_everything(tmp_path):
    s = _ToySentinel(tmp_path)
    assert s.is_enabled()
    with patch.dict(os.environ, {_base.MASTER_KILL_SWITCH_ENV: "1"}):
        assert not s.is_enabled()


# ─── Inbox / notifications ───────────────────────────────────────────────


def test_notify_writes_to_inbox(tmp_path):
    s = _ToySentinel(tmp_path)
    s.notify("warning", "hello", "test message", addressed_to="operator")
    inbox = s.read_inbox(only_unread=True)
    assert len(inbox) == 1
    assert inbox[0].title == "hello"
    assert inbox[0].severity == "warning"
    assert inbox[0].acknowledged is False


def test_acknowledge_marks_all_read(tmp_path):
    s = _ToySentinel(tmp_path)
    s.notify("info", "a", "1")
    s.notify("info", "b", "2")
    count = s.acknowledge_all()
    assert count == 2
    assert s.read_inbox(only_unread=True) == []


# ─── Registry ────────────────────────────────────────────────────────────


def test_registry_includes_cache_sentinel():
    """After package import, the cache sentinel must be registered."""
    ids = _reg.registered_ids()
    assert "cache" in ids


def test_registry_instantiate_returns_correct_class(tmp_path):
    s = _reg.instantiate("cache", tmp_path)
    assert s is not None
    assert s.id == "cache"


def test_registry_unknown_id_returns_none(tmp_path):
    assert _reg.instantiate("does-not-exist", tmp_path) is None


def test_gather_health_returns_one_per_sentinel(tmp_path):
    health = _reg.gather_health(tmp_path)
    assert len(health) == len(_reg.registered_ids())
    for h in health:
        assert h.sentinel_id in _reg.registered_ids()


def test_scan_all_returns_one_report_per_enabled_sentinel(tmp_path):
    reports = _reg.scan_all(tmp_path)
    # Only enabled ones scan (in default test env, all are enabled)
    assert len(reports) >= 1
    for r in reports:
        assert r.sentinel_id in _reg.registered_ids()


# ─── Catalog persistence ─────────────────────────────────────────────────


def test_catalog_save_and_load_roundtrip(tmp_path):
    s = _ToySentinel(tmp_path)
    s.save_catalog({"key": "value", "n": 42}, name="custom")
    loaded = s.load_catalog("custom")
    assert loaded == {"key": "value", "n": 42}


def test_load_catalog_returns_none_when_missing(tmp_path):
    s = _ToySentinel(tmp_path)
    assert s.load_catalog("never-saved") is None
