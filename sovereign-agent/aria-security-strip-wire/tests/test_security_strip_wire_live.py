"""Behavior tests for aria-security-strip-wire, promoted to live tests/ —
tests the REAL, already-patched `sovereign_agent.cockpit.app` directly, no
shadow copy, no `sys.modules` manipulation.

The staged `test_security_strip_wire.py` (which stays in `aria-security-
strip-wire/tests/`, never promoted) uses a shadow-copy-and-patch mechanism
to verify the patch function itself works correctly BEFORE the code is
actually applied to live. Once applied, that mechanism is unnecessary — the
live `app.py` already has the fix baked in permanently — and it turned out
to be actively harmful in the live suite: a real regression was found where
this exact save/delete/restore `sys.modules` dance (needed only for the
pre-apply shadow trick) decoupled shared module-level state (this fix's own
`_SECURITY_SCAN_CACHE`/`_SECURITY_SCAN_LOCK`, and other modules' singletons)
across tests, causing unrelated, timing-sensitive tests elsewhere in the
suite to fail — the exact same class of bug already found and fixed once
this session in `test_locator_events_fix.py`. Root cause fix: don't do it.
Test the real, live module directly, exactly like `test_cockpit.py` does.
"""
from __future__ import annotations

import pytest


def _app_module():
    import sovereign_agent.cockpit.app as app_module
    return app_module


@pytest.mark.asyncio
async def test_security_strip_shows_interim_design_immediately_and_no_scan_starts():
    """On boot, the security scan is NOT kicked off eagerly (see the module
    docstring's "2nd pass" note in patcher.py — the actual fix for the live
    GIL-contention regression) — the strip must show the tier-census
    fallback, and the process-wide running flag must stay False, since
    nothing has triggered a scan yet."""
    from sovereign_agent.cockpit import CockpitApp
    app_module = _app_module()
    original_running = app_module._SECURITY_SCAN_RUNNING
    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        from textual.widgets import Static
        strip = app.query_one("#security-strip", Static)
        rendered = str(strip.render())
        assert "security" in rendered.lower()
        assert "T3" in rendered
        assert app_module._SECURITY_SCAN_RUNNING is False
    assert app_module._SECURITY_SCAN_RUNNING == original_running


@pytest.mark.asyncio
async def test_security_strip_shows_real_scan_counts_once_cache_populated():
    """Once the background worker has populated the cache, the strip must
    show the real block/warn counts, not just the interim tier census.

    The cache is process-wide module state, not a per-instance attribute —
    set/restore it directly on the module, always restoring afterward so
    this test cannot leak state into any other test in the suite."""
    from sovereign_agent.cockpit import CockpitApp
    app_module = _app_module()
    original_cache = app_module._SECURITY_SCAN_CACHE
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app_module._SECURITY_SCAN_CACHE = {"blocks": 2, "warns": 141, "files_scanned": 449}
        try:
            app._refresh_security_strip()
            await pilot.pause()

            from textual.widgets import Static
            strip = app.query_one("#security-strip", Static)
            rendered = str(strip.render())
            assert "2 block" in rendered
            assert "141 warn" in rendered
        finally:
            app_module._SECURITY_SCAN_CACHE = original_cache


@pytest.mark.asyncio
async def test_maybe_run_security_scan_guards_against_overlap():
    """Calling _maybe_run_security_scan while a scan is already marked
    running (process-wide) must not kick off a second worker."""
    from sovereign_agent.cockpit import CockpitApp
    app_module = _app_module()
    original_running = app_module._SECURITY_SCAN_RUNNING
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app_module._SECURITY_SCAN_RUNNING = True
        try:
            called = []
            app._run_security_scan_worker = lambda: called.append(1)
            app._maybe_run_security_scan()
            assert called == []  # guarded — did not fire
        finally:
            app_module._SECURITY_SCAN_RUNNING = original_running


def test_only_one_scan_runs_across_many_app_instances():
    """Regression test for the actual live bug: booting many CockpitApp
    instances in the same process must NOT spawn a competing scan thread
    per instance — the module-level lock means only the FIRST call actually
    starts a worker; every subsequent call (from any instance) is a no-op
    until that one finishes. Always restores the flag afterward."""
    from sovereign_agent.cockpit import CockpitApp
    app_module = _app_module()
    original_running = app_module._SECURITY_SCAN_RUNNING
    app_module._SECURITY_SCAN_RUNNING = False
    try:
        started = []
        for _ in range(5):
            app = CockpitApp()
            app._run_security_scan_worker = lambda: started.append(1)
            app._maybe_run_security_scan()
        assert len(started) == 1  # only the first instance's call actually started a worker
    finally:
        app_module._SECURITY_SCAN_RUNNING = original_running


def test_scan_tree_runs_clean_on_real_src():
    """Sanity: the real scan_tree() function this worker calls actually
    runs without raising against the real, live src/ tree."""
    from pathlib import Path

    import sovereign_agent
    from sovereign_agent.scanner_tier_a.scanner import scan_tree

    src_root = Path(sovereign_agent.__file__).parent
    result = scan_tree(src_root)
    assert result.files_scanned > 0
