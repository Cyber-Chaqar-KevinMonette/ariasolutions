"""Behavior tests for aria-vessel-health (Workstream I) — prove the
patched cockpit + the vessel_health aggregator actually work, using a
shadow copy of the whole package (never touches real src/). STAGED ONLY:
never promoted — see test_vessel_health_live.py for the promoted copy."""
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
    for candidate in (start, *start.parents):
        if (candidate / "aria-vessel-health" / "patcher.py").is_file():
            return candidate / "aria-vessel-health"
    raise RuntimeError("could not locate aria-vessel-health/ from " + str(start))


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
    app_py.write_text(patched, encoding="utf-8")

    vh_src = STAGING / "payload" / "src" / "sovereign_agent" / "vessel_health.py"
    (shadow / "sovereign_agent" / "vessel_health.py").write_text(
        vh_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return shadow


@pytest.fixture
def shadow_pkg(tmp_path, monkeypatch):
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
        import sovereign_agent
        yield sovereign_agent
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


# ── vessel_health.py aggregator tests ───────────────────────────────────


def test_gather_vessel_health_returns_a_report_on_a_fresh_data_dir(shadow_pkg, tmp_path):
    from sovereign_agent.vessel_health import gather_vessel_health

    report = gather_vessel_health(
        data_dir=tmp_path / "data", repo_root=tmp_path, include_kernel_coherence=False,
    )
    assert report.kernel_coherence_ratio is None  # not requested
    assert report.signal_avg_confidence is None  # no beliefs yet
    assert report.flourishing_applied == 0
    assert report.flourishing_quarantined == 0


def test_gather_vessel_health_reads_real_beliefs(shadow_pkg, tmp_path):
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


def test_gather_vessel_health_reads_flourishing_trend(shadow_pkg, tmp_path):
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


def test_gather_vessel_health_never_raises_on_totally_empty_data_dir(shadow_pkg, tmp_path):
    from sovereign_agent.vessel_health import gather_vessel_health

    # A data dir that doesn't exist yet at all — must degrade gracefully.
    report = gather_vessel_health(
        data_dir=tmp_path / "does-not-exist-yet",
        repo_root=tmp_path,
        include_kernel_coherence=False,
    )
    assert report is not None


def test_kernel_coherence_included_when_requested(shadow_pkg, tmp_path):
    from sovereign_agent.vessel_health import gather_vessel_health

    report = gather_vessel_health(
        data_dir=tmp_path / "data", repo_root=REPO_ROOT, include_kernel_coherence=True,
    )
    assert report.kernel_coherence_ratio is not None
    assert 0.0 <= report.kernel_coherence_ratio <= 1.0


# ── cockpit pane / strip tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_vessel_strip_exists_and_renders_without_throwing(shadow_pkg):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        strip = app.query_one("#vessel-strip", Static)
        rendered = strip.render()
        assert rendered is not None


@pytest.mark.asyncio
async def test_vessel_strip_shows_scanning_placeholder_before_kernel_cache_populated(shadow_pkg):
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
async def test_vessel_kernel_scan_not_triggered_eagerly_on_mount(shadow_pkg):
    """Regression guard mirroring the exact GIL-contention bug already
    found once this session: booting the app must NOT start the kernel-
    coherence scan — only the 300s timer may."""
    from sovereign_agent.cockpit import CockpitApp
    import sovereign_agent.cockpit.app as app_module

    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        assert app_module._VESSEL_KERNEL_RUNNING is False


@pytest.mark.asyncio
async def test_maybe_run_vessel_kernel_scan_guards_against_overlap(shadow_pkg):
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
async def test_vessel_strip_shows_real_values_once_cache_populated(shadow_pkg):
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
