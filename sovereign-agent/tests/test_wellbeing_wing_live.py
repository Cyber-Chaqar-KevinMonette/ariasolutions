"""aria-wellbeing-wing — proving wing + close-out + extensibility retrofit.
(Wellbeing round · W5)

`wellbeing_wing.py` is a brand-new submodule inside the already-live
`proving_ground` package — reachable pre-apply via path extension. The
runner.py wiring (SUITE_VERSION bump + tail import) and the three
extension-seam retrofits are IN-PLACE patches — patch-dependent, skip
honestly pre-apply; the apply script re-runs this file and requires zero
skips.
"""
from __future__ import annotations

import inspect

import pytest

MARK = "wellbeing-wing-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


# ─── the five tasks, each real and standalone ────────────────────────────


@pytest.mark.asyncio
async def test_wellbeing_pass_persists_task_passes():
    from sovereign_agent.proving_ground.wellbeing_wing import (
        _task_wellbeing_pass_persists,
    )

    ok, note = await _task_wellbeing_pass_persists()
    assert ok, note


@pytest.mark.asyncio
async def test_wellbeing_gate_blocks_task_passes():
    from sovereign_agent.proving_ground.wellbeing_wing import (
        _task_wellbeing_gate_blocks,
    )

    ok, note = await _task_wellbeing_gate_blocks()
    assert ok, note


@pytest.mark.asyncio
async def test_wellbeing_diagnosis_readable_task_passes():
    from sovereign_agent.proving_ground.wellbeing_wing import (
        _task_wellbeing_diagnosis_readable,
    )

    ok, note = await _task_wellbeing_diagnosis_readable()
    assert ok, note


@pytest.mark.asyncio
async def test_wellbeing_angel_measured_task_passes():
    from sovereign_agent.proving_ground.wellbeing_wing import (
        _task_wellbeing_angel_measured,
    )

    ok, note = await _task_wellbeing_angel_measured()
    assert ok, note


@pytest.mark.asyncio
async def test_wellbeing_pass_gates_task_passes():
    from sovereign_agent.proving_ground.wellbeing_wing import _task_wellbeing_pass_gates

    ok, note = await _task_wellbeing_pass_gates()
    assert ok, note


def test_wellbeing_tasks_dict_has_all_five():
    from sovereign_agent.proving_ground.wellbeing_wing import WELLBEING_TASKS

    assert len(WELLBEING_TASKS) == 5
    assert all(k.startswith("wellbeing-") for k in WELLBEING_TASKS)


# ─── the runner.py wiring ─────────────────────────────────────────────────


def test_suite_version_has_advanced_past_v5_once_patched():
    """SUITE_VERSION itself is not this test's concern — it keeps bumping
    as later wings get added; pinning an exact string here would break on
    every unrelated future version bump (this bit the Quality round's own
    Q5 test once already, then the Grounding round's own G5 test too).
    What matters is that W5's bump landed."""
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    assert runner.SUITE_VERSION not in ("v1", "v2", "v3", "v4", "v5")


def test_wellbeing_tasks_folded_into_offline_tasks_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    from sovereign_agent.proving_ground.wellbeing_wing import WELLBEING_TASKS

    for task_id in WELLBEING_TASKS:
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


# ─── extensibility retrofit (patch-dependent) ────────────────────────────


def test_msims_has_the_extension_seam():
    from sovereign_agent.stewardship import msims as msims_module

    if not _patched(msims_module):
        pytest.skip("pre-apply: stewardship/msims.py seam not yet added")
    assert "Relational" in inspect.getsource(msims_module)


def test_calibration_has_the_extension_seam():
    from sovereign_agent.stewardship import calibration as calibration_module

    if not _patched(calibration_module):
        pytest.skip("pre-apply: stewardship/calibration.py seam not yet added")
    assert MARK in inspect.getsource(calibration_module.honor_score)


def test_companion_tools_has_the_extension_seam():
    from sovereign_agent.tools import companion_tools

    if not _patched(companion_tools):
        pytest.skip("pre-apply: companion_tools.py seam not yet added")
    assert MARK in inspect.getsource(companion_tools._build_value_report)
