"""Behavior tests for aria-proving-ground, promoted to live tests/ — the
offline suite IS the pytest surface (real machinery, scripted clients).

Every test passes an isolated tmp_path as data_dir. Without this, running
the suite writes real entries into the production results.ndjson (the
actual history the running system's own trend-reporting reads from) and
the second test's "insufficient-history" assertion is only true the very
first time the suite is ever run on a machine — false on any real,
long-running install with accumulated proving-ground history."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_offline_suite_runs_scores_and_persists(tmp_path):
    from sovereign_agent.proving_ground import latest_scores, run_offline_suite

    result = await run_offline_suite(data_dir=tmp_path)
    assert result.tasks, "no tasks ran"
    # THE bar: on a healthy tree every offline task passes.
    failed = {k: v for k, v in result.tasks.items() if not v["pass"]}
    assert not failed, failed
    stored = latest_scores(1, data_dir=tmp_path)
    assert stored and stored[0]["run_id"] == result.run_id
    assert stored[0]["score"] == 1.0


@pytest.mark.asyncio
async def test_trend_comes_from_stored_scores(tmp_path):
    from sovereign_agent.proving_ground import run_offline_suite, trend

    assert trend(data_dir=tmp_path) == "insufficient-history"
    await run_offline_suite(data_dir=tmp_path)
    await run_offline_suite(data_dir=tmp_path)
    assert trend(data_dir=tmp_path) in ("stable", "improving")


@pytest.mark.asyncio
async def test_a_crashing_task_is_a_fail_never_a_run_crash(monkeypatch, tmp_path):
    from sovereign_agent.proving_ground import runner

    async def _boom():
        raise RuntimeError("scorer exploded")

    monkeypatch.setitem(runner.OFFLINE_TASKS, "exploding-task", _boom)
    result = await runner.run_offline_suite(data_dir=tmp_path)
    assert result.tasks["exploding-task"]["pass"] is False
    assert "crashed" in result.tasks["exploding-task"]["note"]
