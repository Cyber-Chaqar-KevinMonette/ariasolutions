"""aria-memory-proof — the proving ground's memory wing. (FABLE II · M4)

Each task is run for real (isolated SETTINGS) and must PASS — these are
the scored proofs, so the tests hold them to a passing standard, not just
an executing one.
"""
from __future__ import annotations

import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_cross_restart_recall_passes():
    from sovereign_agent.proving_ground.memory_wing import _task_cross_restart_recall

    ok, note = _run(_task_cross_restart_recall())
    assert ok, note


def test_lesson_roundtrip_passes_and_cleans_up():
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.proving_ground.memory_wing import _task_lesson_roundtrip

    ok, note = _run(_task_lesson_roundtrip())
    assert ok, note
    conn = open_atoms_db()
    try:
        n = conn.execute("SELECT COUNT(*) FROM lessons WHERE trigger = ?",
                         ("prove-d:roundtrip",)).fetchone()[0]
    finally:
        conn.close()
    assert n == 0   # the scaffolding row was removed


def test_journal_once_only_passes(monkeypatch):
    monkeypatch.delenv("SOV_NO_JOURNAL", raising=False)
    from sovereign_agent.proving_ground.memory_wing import _task_journal_once_only

    ok, note = _run(_task_journal_once_only())
    assert ok, note


def test_one_truth_clean_passes():
    from sovereign_agent.proving_ground.memory_wing import _task_one_truth_clean

    ok, note = _run(_task_one_truth_clean())
    assert ok, note


def test_compaction_recall_passes(monkeypatch):
    monkeypatch.delenv("SOV_NO_COMPACT", raising=False)
    monkeypatch.delenv("SOV_NO_COMPACT_QA", raising=False)
    from sovereign_agent.proving_ground.memory_wing import (
        _task_compaction_preserves_recall,
    )

    ok, note = _run(_task_compaction_preserves_recall())
    assert ok, note


def test_memory_tasks_registry_names_all_five():
    from sovereign_agent.proving_ground.memory_wing import MEMORY_TASKS

    assert set(MEMORY_TASKS) == {
        "cross-restart-recall", "lesson-roundtrip", "journal-once-only",
        "one-truth-clean", "compaction-recall",
    }


def test_offline_suite_carries_the_wing_once_applied():
    """Post-apply: the runner's OFFLINE_TASKS includes the wing and the
    suite version is v2 (stored scores name the suite they scored)."""
    import inspect

    import pytest

    from sovereign_agent.proving_ground import runner

    if "memory-proof-d" not in inspect.getsource(runner):
        pytest.skip("pre-apply: runner not yet patched "
                    "(the apply script re-runs this file after patching)")
    assert runner.SUITE_VERSION == "v2"
    for task_id in ("cross-restart-recall", "lesson-roundtrip",
                    "journal-once-only", "one-truth-clean", "compaction-recall"):
        assert task_id in runner.OFFLINE_TASKS
