"""aria-timeout-wing — proving wing + close-out. (Timeout round · T4)

`timeout_wing.py` is a brand-new submodule inside the already-live
`proving_ground` package — reachable pre-apply via path extension. The
runner.py wiring (SUITE_VERSION bump + tail import) is an IN-PLACE
patch — patch-dependent, skip honestly pre-apply; the apply script
re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect

import pytest

MARK = "timeout-wing-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


@pytest.mark.asyncio
async def test_timeout_scan_persists_task_passes():
    from sovereign_agent.proving_ground.timeout_wing import _task_timeout_scan_persists

    ok, note = await _task_timeout_scan_persists()
    assert ok, note


@pytest.mark.asyncio
async def test_timeout_gate_blocks_task_passes():
    from sovereign_agent.proving_ground.timeout_wing import _task_timeout_gate_blocks

    ok, note = await _task_timeout_gate_blocks()
    assert ok, note


@pytest.mark.asyncio
async def test_timeout_diagnosis_readable_task_passes():
    from sovereign_agent.proving_ground.timeout_wing import _task_timeout_diagnosis_readable

    ok, note = await _task_timeout_diagnosis_readable()
    assert ok, note


@pytest.mark.asyncio
async def test_timeout_catalogued_justified_task_passes():
    from sovereign_agent.proving_ground.timeout_wing import _task_timeout_catalogued_justified

    ok, note = await _task_timeout_catalogued_justified()
    assert ok, note


@pytest.mark.asyncio
async def test_timeout_uncatalogued_unexplained_task_passes():
    from sovereign_agent.proving_ground.timeout_wing import (
        _task_timeout_uncatalogued_unexplained,
    )

    ok, note = await _task_timeout_uncatalogued_unexplained()
    assert ok, note


def test_timeout_tasks_dict_has_all_five():
    from sovereign_agent.proving_ground.timeout_wing import TIMEOUT_TASKS

    assert len(TIMEOUT_TASKS) == 5
    assert all(k.startswith("timeout-") for k in TIMEOUT_TASKS)


def test_suite_version_has_advanced_past_v7_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    assert runner.SUITE_VERSION not in ("v1", "v2", "v3", "v4", "v5", "v6", "v7")


def test_timeout_tasks_folded_into_offline_tasks_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    from sovereign_agent.proving_ground.timeout_wing import TIMEOUT_TASKS

    for task_id in TIMEOUT_TASKS:
        assert task_id in runner.OFFLINE_TASKS


@pytest.mark.asyncio
async def test_full_offline_suite_all_pass_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    result = await runner.run_offline_suite()
    failed = {k: v for k, v in result.tasks.items() if not v["pass"]}
    assert not failed, failed
    assert result.suite == runner.SUITE_VERSION
