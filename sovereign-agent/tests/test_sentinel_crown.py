"""Tests for M55 sentinel-crown — activating the dormant sentinel squad."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ─── Registry alias ──────────────────────────────────────────────────────────

def test_sentinel_registry_alias_exported():
    from sovereign_agent.stewardship.registry import SENTINEL_REGISTRY
    assert isinstance(SENTINEL_REGISTRY, dict)


def test_sentinel_registry_alias_is_same_object():
    from sovereign_agent.stewardship.registry import SENTINEL_REGISTRY, _REGISTRY
    assert SENTINEL_REGISTRY is _REGISTRY


# ─── All 8 dormant sentinels importable ──────────────────────────────────────

def test_watchdog_sentinel_importable():
    from sovereign_agent.stewardship import watchdog_sentinel  # noqa: F401


def test_conformance_sentinel_importable():
    from sovereign_agent.stewardship import conformance_sentinel  # noqa: F401


def test_defense_sentinel_importable():
    from sovereign_agent.stewardship import defense_sentinel  # noqa: F401


def test_memory_garden_importable():
    from sovereign_agent.stewardship import memory_garden  # noqa: F401


def test_passive_watcher_importable():
    from sovereign_agent.stewardship import passive_watcher_sentinel  # noqa: F401


def test_phantom_sentinel_importable():
    from sovereign_agent.stewardship import phantom_sentinel  # noqa: F401


def test_locator_sentinel_importable():
    from sovereign_agent.stewardship import locator_sentinel  # noqa: F401


def test_roster_sentinel_importable():
    from sovereign_agent.stewardship import roster_sentinel  # noqa: F401


# ─── Registry completeness ───────────────────────────────────────────────────

def test_registered_ids_includes_all_new_sentinels():
    from sovereign_agent.stewardship.registry import registered_ids
    ids = registered_ids()
    # Original 3
    assert "cache" in ids
    assert "telemetry" in ids
    assert "atoms-compact" in ids
    # New 7 (memory_garden is a utility module, not a sentinel)
    assert "watchdog" in ids
    assert "conformance" in ids
    assert "defense" in ids
    assert "passive_watcher" in ids   # uses underscore (its declared id)
    assert "phantom" in ids
    assert "locator" in ids
    assert "roster" in ids


def test_registered_count_at_least_10():
    from sovereign_agent.stewardship.registry import registered_ids
    assert len(registered_ids()) >= 10  # 3 original + 7 new sentinels


# ─── Aggregate operations work with expanded registry ────────────────────────

def test_gather_health_includes_all_sentinels():
    from sovereign_agent.stewardship.registry import gather_health
    with tempfile.TemporaryDirectory() as tmpdir:
        health = gather_health(Path(tmpdir))
    assert len(health) >= 10
    ids_in_health = {h.sentinel_id for h in health}
    assert "watchdog" in ids_in_health
    assert "conformance" in ids_in_health
    assert "roster" in ids_in_health


def test_scan_all_no_crash():
    from sovereign_agent.stewardship.registry import scan_all
    with tempfile.TemporaryDirectory() as tmpdir:
        reports = scan_all(Path(tmpdir))
    # scan_all soft-fails; we just need it to not raise
    assert isinstance(reports, list)


def test_instantiate_all_returns_correct_count():
    from sovereign_agent.stewardship.registry import instantiate_all
    with tempfile.TemporaryDirectory() as tmpdir:
        instances = instantiate_all(Path(tmpdir))
    assert len(instances) >= 10
