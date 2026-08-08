"""Behavior tests for aria-vessel-health, promoted to live tests/ — tests
the REAL, already-patched `sovereign_agent.cockpit.app` /
`sovereign_agent.vessel_health` directly, no shadow copy, no `sys.modules`
manipulation. See test_vessel_health.py (staged only) for the shadow-copy
pre-apply verification version.
"""
from __future__ import annotations

import pytest


# ── vessel_health.py aggregator tests ───────────────────────────────────


def test_gather_vessel_health_returns_a_report_on_a_fresh_data_dir(tmp_path):
    from sovereign_agent.vessel_health import gather_vessel_health

    report = gather_vessel_health(
        data_dir=tmp_path / "data", repo_root=tmp_path, include_kernel_coherence=False,
    )
    assert report.kernel_coherence_ratio is None
    assert report.signal_avg_confidence is None
    assert report.flourishing_applied == 0
    assert report.flourishing_quarantined == 0


def test_gather_vessel_health_reads_real_beliefs(tmp_path):
    from sovereign_agent.epistemic_ledger.ledger import EpistemicLedger
    from sovereign_agent.vessel_health import gather_vessel_health

    data_dir = tmp_path / "data"
    ledger = EpistemicLedger(data_dir / "epistemic")
    ledger.record("the sky is blue", 0.9, evidence_refs=[])
    ledger.record("aliens run the moon", 0.1, evidence_refs=[])

    report = gather_vessel_health(
        data_dir=data_dir, repo_root=tmp_path, include_kernel_coherence=False,
    )
    assert report.signal_belief_count == 2
    assert report.signal_avg_confidence == pytest.approx(0.5, abs=0.01)


def test_gather_vessel_health_reads_flourishing_trend(tmp_path):
    from sovereign_agent.apply_queue.store import ApplyQueueStore, QuarantineRegistry
    from sovereign_agent.vessel_health import gather_vessel_health

    data_dir = tmp_path / "data"
    store = ApplyQueueStore(data_dir / "apply_queue")
    store.enqueue(["aria-foo", "aria-bar"])
    store.mark("aria-foo", "applied")
    store.mark("aria-bar", "quarantined")

    quarantine = QuarantineRegistry(data_dir / "quarantine")
    quarantine.quarantine("aria-bar", "rollback triggered")

    report = gather_vessel_health(
        data_dir=data_dir, repo_root=tmp_path, include_kernel_coherence=False,
    )
    assert report.flourishing_applied == 1
    assert report.flourishing_quarantined == 1


def test_gather_vessel_health_never_raises_on_totally_empty_data_dir(tmp_path):
    from sovereign_agent.vessel_health import gather_vessel_health

    report = gather_vessel_health(
        data_dir=tmp_path / "does-not-exist-yet",
        repo_root=tmp_path,
        include_kernel_coherence=False,
    )
    assert report is not None


def test_kernel_coherence_included_when_requested(tmp_path):
    from pathlib import Path

    import sovereign_agent
    from sovereign_agent.vessel_health import gather_vessel_health

    repo_root = Path(sovereign_agent.__file__).parent.parent.parent
    report = gather_vessel_health(
        data_dir=tmp_path / "data", repo_root=repo_root, include_kernel_coherence=True,
    )
    assert report.kernel_coherence_ratio is not None
    assert 0.0 <= report.kernel_coherence_ratio <= 1.0


# ── cockpit pane / strip tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_vessel_strip_exists_and_renders_without_throwing():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        strip = app.query_one("#vessel-strip", Static)
        rendered = strip.render()
        assert rendered is not None


@pytest.mark.asyncio
async def test_vessel_strip_shows_scanning_placeholder_before_kernel_cache_populated():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._refresh_vessel_strip()
        await pilot.pause()
        strip = app.query_one("#vessel-strip", Static)
        rendered = str(strip.render())
        assert "vessel" in rendered.lower()
        assert "scanning" in rendered.lower()


@pytest.mark.asyncio
async def test_vessel_kernel_scan_not_triggered_eagerly_on_mount():
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.cockpit.app as app_module

    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        assert app_module._VESSEL_KERNEL_RUNNING is False


@pytest.mark.asyncio
async def test_maybe_run_vessel_kernel_scan_guards_against_overlap():
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.cockpit.app as app_module

    original = app_module._VESSEL_KERNEL_RUNNING
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app_module._VESSEL_KERNEL_RUNNING = True
        try:
            called = []
            app._run_vessel_kernel_scan_worker = lambda: called.append(1)
            app._maybe_run_vessel_kernel_scan()
            assert called == []
        finally:
            app_module._VESSEL_KERNEL_RUNNING = original


@pytest.mark.asyncio
async def test_vessel_strip_shows_real_values_once_cache_populated():
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.cockpit.app as app_module
    from textual.widgets import Static

    original = app_module._VESSEL_KERNEL_CACHE
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app_module._VESSEL_KERNEL_CACHE = {"ratio": 0.25, "summary": "9/35 clauses"}
        try:
            app._refresh_vessel_strip()
            await pilot.pause()
            strip = app.query_one("#vessel-strip", Static)
            rendered = str(strip.render())
            assert "25%" in rendered
        finally:
            app_module._VESSEL_KERNEL_CACHE = original
