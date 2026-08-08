"""aria-integrity-wing — proving wing + close-out. (Integrity round · I5)

`integrity_wing.py` is a brand-new submodule inside the already-live
`proving_ground` package — reachable pre-apply via path extension. The
runner.py wiring (SUITE_VERSION bump + tail import) is an IN-PLACE
patch — patch-dependent, skip honestly pre-apply; the apply script
re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect

import pytest

MARK = "integrity-wing-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


# ─── the five tasks, each real and standalone ────────────────────────────


@pytest.mark.asyncio
async def test_integrity_pass_persists_task_passes():
    from sovereign_agent.proving_ground.integrity_wing import _task_integrity_pass_persists

    ok, note = await _task_integrity_pass_persists()
    assert ok, note


@pytest.mark.asyncio
async def test_integrity_gate_blocks_task_passes():
    from sovereign_agent.proving_ground.integrity_wing import _task_integrity_gate_blocks

    ok, note = await _task_integrity_gate_blocks()
    assert ok, note


@pytest.mark.asyncio
async def test_integrity_diagnosis_readable_task_passes():
    from sovereign_agent.proving_ground.integrity_wing import (
        _task_integrity_diagnosis_readable,
    )

    ok, note = await _task_integrity_diagnosis_readable()
    assert ok, note


@pytest.mark.asyncio
async def test_integrity_witness_measured_task_passes():
    from sovereign_agent.proving_ground.integrity_wing import (
        _task_integrity_witness_measured,
    )

    ok, note = await _task_integrity_witness_measured()
    assert ok, note


@pytest.mark.asyncio
async def test_integrity_pass_gates_task_passes():
    from sovereign_agent.proving_ground.integrity_wing import _task_integrity_pass_gates

    ok, note = await _task_integrity_pass_gates()
    assert ok, note


def test_integrity_tasks_dict_has_all_five():
    from sovereign_agent.proving_ground.integrity_wing import INTEGRITY_TASKS

    assert len(INTEGRITY_TASKS) == 5
    assert all(k.startswith("integrity-") for k in INTEGRITY_TASKS)


# ─── the runner.py wiring ─────────────────────────────────────────────────


def test_suite_version_has_advanced_past_v6_once_patched():
    """SUITE_VERSION itself is not this test's concern — it keeps bumping
    as later wings get added; pinning an exact string here would break on
    every unrelated future version bump (this bit the Quality/Grounding/
    Wellbeing rounds' own wing tests already). What matters is that I5's
    bump landed."""
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    assert runner.SUITE_VERSION not in ("v1", "v2", "v3", "v4", "v5", "v6")


def test_integrity_tasks_folded_into_offline_tasks_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    from sovereign_agent.proving_ground.integrity_wing import INTEGRITY_TASKS

    for task_id in INTEGRITY_TASKS:
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
