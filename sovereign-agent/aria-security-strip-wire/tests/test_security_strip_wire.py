"""Behavior tests for aria-security-strip-wire — prove the security strip
actually surfaces J's real Tier-A scanner findings after the background
scan completes, using a shadow copy of the whole package (never touches
real src/)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    """Robust to running from either the staged location (aria-security-
    strip-wire/tests/) or the promoted live location (tests/), which differ
    in nesting depth — the same path-depth bug class fixed elsewhere this
    session (test_command_menu.py, test_tools_all_export_fix.py, etc.)."""
    for candidate in (start, *start.parents):
        if (candidate / "aria-security-strip-wire" / "patcher.py").is_file():
            return candidate / "aria-security-strip-wire"
    raise RuntimeError("could not locate aria-security-strip-wire/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_app

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    app_py = shadow / "sovereign_agent" / "cockpit" / "app.py"
    patched, _ = patch_app(app_py.read_text(encoding="utf-8"))
    from patcher import MARK
    assert MARK in patched
    app_py.write_text(patched, encoding="utf-8")
    return shadow


@pytest.fixture
def shadow_cockpit(tmp_path, monkeypatch):
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent.cockpit.app as shadow_app_mod
        yield shadow_app_mod
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


@pytest.mark.asyncio
async def test_security_strip_shows_interim_design_immediately_and_no_scan_starts(shadow_cockpit):
    """On boot, the security scan is NOT kicked off eagerly (see the module
    docstring's "2nd pass" note — this is the actual fix for the live
    GIL-contention regression) — the strip must show the tier-census
    fallback, and the process-wide running flag must stay False, since
    nothing has triggered a scan yet."""
    app_cls = shadow_cockpit.CockpitApp
    original_running = shadow_cockpit._SECURITY_SCAN_RUNNING
    async with app_cls().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        from textual.widgets import Static
        strip = app.query_one("#security-strip", Static)
        rendered = str(strip.render())
        assert "security" in rendered.lower()
        assert "T3" in rendered
        assert shadow_cockpit._SECURITY_SCAN_RUNNING is False
    assert shadow_cockpit._SECURITY_SCAN_RUNNING == original_running


@pytest.mark.asyncio
async def test_security_strip_shows_real_scan_counts_once_cache_populated(shadow_cockpit):
    """Once the background worker has populated the cache, the strip must
    show the real block/warn counts, not just the interim tier census.

    The cache is process-wide module state (see the module-level-vs-
    instance-attribute regression test in test_patcher.py), not a
    per-instance attribute — set/restore it directly on the module."""
    app_cls = shadow_cockpit.CockpitApp
    original_cache = shadow_cockpit._SECURITY_SCAN_CACHE
    async with app_cls().run_test() as pilot:
        app = pilot.app
        # Simulate the background worker having already completed a scan.
        shadow_cockpit._SECURITY_SCAN_CACHE = {"blocks": 2, "warns": 141, "files_scanned": 449}
        try:
            app._refresh_security_strip()
            await pilot.pause()

            from textual.widgets import Static
            strip = app.query_one("#security-strip", Static)
            rendered = str(strip.render())
            assert "2 block" in rendered
            assert "141 warn" in rendered
        finally:
            shadow_cockpit._SECURITY_SCAN_CACHE = original_cache


@pytest.mark.asyncio
async def test_maybe_run_security_scan_guards_against_overlap(shadow_cockpit):
    """Calling _maybe_run_security_scan while a scan is already marked
    running (process-wide) must not kick off a second worker."""
    app_cls = shadow_cockpit.CockpitApp
    original_running = shadow_cockpit._SECURITY_SCAN_RUNNING
    async with app_cls().run_test() as pilot:
        app = pilot.app
        shadow_cockpit._SECURITY_SCAN_RUNNING = True
        try:
            called = []
            app._run_security_scan_worker = lambda: called.append(1)
            app._maybe_run_security_scan()
            assert called == []  # guarded — did not fire
        finally:
            shadow_cockpit._SECURITY_SCAN_RUNNING = original_running


def test_only_one_scan_runs_across_many_app_instances(shadow_cockpit):
    """Regression test for the actual live bug: booting many CockpitApp
    instances in the same process must NOT spawn a competing scan thread
    per instance — the module-level lock means only the FIRST call actually
    starts a worker; every subsequent call (from any instance) is a no-op
    until that one finishes."""
    app_cls = shadow_cockpit.CockpitApp
    original_running = shadow_cockpit._SECURITY_SCAN_RUNNING
    shadow_cockpit._SECURITY_SCAN_RUNNING = False
    try:
        started = []
        for _ in range(5):
            app = app_cls()
            app._run_security_scan_worker = lambda: started.append(1)
            app._maybe_run_security_scan()
        assert len(started) == 1  # only the first instance's call actually started a worker
    finally:
        shadow_cockpit._SECURITY_SCAN_RUNNING = original_running


def test_scan_tree_runs_clean_on_the_shadow_src(tmp_path):
    """Sanity: the real scan_tree() function this worker calls actually
    runs without raising against a real src/ tree (the shadow copy)."""
    shadow = _build_shadow(tmp_path)
    sys.path.insert(0, str(shadow))
    try:
        import importlib
        scanner_mod = importlib.import_module("sovereign_agent.scanner_tier_a.scanner")
        result = scanner_mod.scan_tree(shadow / "sovereign_agent")
        assert result.files_scanned > 0
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
