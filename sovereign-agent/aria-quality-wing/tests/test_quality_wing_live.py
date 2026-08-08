"""aria-quality-wing — proving-ground wing + round close-out.
(Quality round · Q5)

`quality_wing.py` is a brand-new submodule inside the already-live
`proving_ground` package — reachable pre-apply via path extension (see
conftest.py's `subpkgs=("proving_ground",)`). The runner.py wiring
(SUITE_VERSION bump + tail import) is an IN-PLACE patch — patch-dependent,
skips honestly pre-apply; the apply script re-runs this file and requires
zero skips.
"""
from __future__ import annotations

import inspect

import pytest

MARK = "quality-tribunal-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


# ─── the five tasks, each real and standalone ────────────────────────────


@pytest.mark.asyncio
async def test_hardening_persists_task_passes():
    from sovereign_agent.proving_ground.quality_wing import _task_hardening_persists

    ok, note = await _task_hardening_persists()
    assert ok, note


@pytest.mark.asyncio
async def test_gate_blocks_bad_task_passes():
    from sovereign_agent.proving_ground.quality_wing import _task_gate_blocks_bad

    ok, note = await _task_gate_blocks_bad()
    assert ok, note


@pytest.mark.asyncio
async def test_diagnosis_readable_task_passes():
    from sovereign_agent.proving_ground.quality_wing import _task_diagnosis_readable

    ok, note = await _task_diagnosis_readable()
    assert ok, note


@pytest.mark.asyncio
async def test_artisan_measured_task_passes():
    from sovereign_agent.proving_ground.quality_wing import _task_artisan_measured

    ok, note = await _task_artisan_measured()
    assert ok, note


@pytest.mark.asyncio
async def test_quality_pass_gates_task_passes():
    from sovereign_agent.proving_ground.quality_wing import _task_quality_pass_gates

    ok, note = await _task_quality_pass_gates()
    assert ok, note


def test_quality_tasks_dict_has_all_five():
    from sovereign_agent.proving_ground.quality_wing import QUALITY_TASKS

    assert len(QUALITY_TASKS) == 5
    assert all(k.startswith("quality-") for k in QUALITY_TASKS)


# ─── the runner.py wiring ─────────────────────────────────────────────────


def test_suite_version_has_advanced_past_v3_once_patched():
    """SUITE_VERSION itself is not this test's concern — it keeps bumping
    as later wings (e.g. the Grounding round's G5) get added; pinning an
    exact string here made this test break on every unrelated version
    bump. What matters is that Q5's own bump landed at all."""
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    assert runner.SUITE_VERSION not in ("v1", "v2", "v3")


def test_quality_tasks_folded_into_offline_tasks_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    from sovereign_agent.proving_ground.quality_wing import QUALITY_TASKS

    for task_id in QUALITY_TASKS:
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
