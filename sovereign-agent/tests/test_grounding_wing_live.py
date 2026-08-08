"""aria-grounding-wing — proving wing + close-out + extensibility retrofit.
(Grounding round · G5)

`grounding_wing.py` is a brand-new submodule inside the already-live
`proving_ground` package — reachable pre-apply via path extension. The
runner.py wiring (SUITE_VERSION bump + tail import) and the three
extension-seam retrofits are IN-PLACE patches — patch-dependent, skip
honestly pre-apply; the apply script re-runs this file and requires zero
skips.
"""
from __future__ import annotations

import inspect

import pytest

MARK = "grounding-wing-d"


def _patched(obj) -> bool:
    return MARK in inspect.getsource(obj)


# ─── the five tasks, each real and standalone ────────────────────────────


@pytest.mark.asyncio
async def test_grounding_pass_persists_task_passes():
    from sovereign_agent.proving_ground.grounding_wing import (
        _task_grounding_pass_persists,
    )

    ok, note = await _task_grounding_pass_persists()
    assert ok, note


@pytest.mark.asyncio
async def test_grounding_gate_blocks_task_passes():
    from sovereign_agent.proving_ground.grounding_wing import (
        _task_grounding_gate_blocks,
    )

    ok, note = await _task_grounding_gate_blocks()
    assert ok, note


@pytest.mark.asyncio
async def test_grounding_diagnosis_readable_task_passes():
    from sovereign_agent.proving_ground.grounding_wing import (
        _task_grounding_diagnosis_readable,
    )

    ok, note = await _task_grounding_diagnosis_readable()
    assert ok, note


@pytest.mark.asyncio
async def test_grounding_skeptic_measured_task_passes():
    from sovereign_agent.proving_ground.grounding_wing import (
        _task_grounding_skeptic_measured,
    )

    ok, note = await _task_grounding_skeptic_measured()
    assert ok, note


@pytest.mark.asyncio
async def test_grounding_pass_gates_task_passes():
    from sovereign_agent.proving_ground.grounding_wing import _task_grounding_pass_gates

    ok, note = await _task_grounding_pass_gates()
    assert ok, note


def test_grounding_tasks_dict_has_all_five():
    from sovereign_agent.proving_ground.grounding_wing import GROUNDING_TASKS

    assert len(GROUNDING_TASKS) == 5
    assert all(k.startswith("grounding-") for k in GROUNDING_TASKS)


# ─── the runner.py wiring ─────────────────────────────────────────────────


def test_suite_version_has_advanced_past_v4_once_patched():
    """SUITE_VERSION itself is not this test's concern — it keeps bumping
    as later wings get added; pinning an exact string here would break on
    every unrelated future version bump (this bit the Quality round's own
    Q5 test once already). What matters is that G5's bump landed."""
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    assert runner.SUITE_VERSION not in ("v1", "v2", "v3", "v4")


def test_grounding_tasks_folded_into_offline_tasks_once_patched():
    from sovereign_agent.proving_ground import runner

    if not _patched(runner):
        pytest.skip("pre-apply: runner.py not yet patched")
    from sovereign_agent.proving_ground.grounding_wing import GROUNDING_TASKS

    for task_id in GROUNDING_TASKS:
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


def test_tribunal_grounding_has_the_extension_seam():
    from sovereign_agent.tribunal import grounding as grounding_module

    if not _patched(grounding_module):
        pytest.skip("pre-apply: tribunal/grounding.py seam not yet added")
    assert MARK in inspect.getsource(grounding_module.analyze)


def test_epistemic_ledger_has_the_extension_seam():
    from sovereign_agent.epistemic_ledger import ledger as epistemic_module

    if not _patched(epistemic_module):
        pytest.skip("pre-apply: epistemic_ledger/ledger.py seam not yet added")
    # the seam is a class-level comment right after current_beliefs() —
    # inspect.getsource on that one method wouldn't include a trailing
    # dangling comment; the module's own source is the honest check.
    assert MARK in inspect.getsource(epistemic_module)


def test_curiosity_has_the_extension_seam():
    from sovereign_agent import curiosity as curiosity_module

    if not _patched(curiosity_module):
        pytest.skip("pre-apply: curiosity.py seam not yet added")
    assert MARK in inspect.getsource(curiosity_module.wonder)
