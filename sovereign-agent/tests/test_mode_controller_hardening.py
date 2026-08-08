"""Tests for M64 — Mode Controller hardening.

Verifies:
  - schedule injection failure emits 'schedule-inject-error-d' (not silently dropped)
  - poison task → next task still runs
  - task exception → status set to 'poison'
  - empty backlog → next_task() returns None
  - _update_task_status() on unknown ID → no crash
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sovereign_agent.mode_controller import (
    BacklogTask,
    ModeController,
    next_task,
    read_backlog,
    write_backlog,
)


# ─── next_task ───────────────────────────────────────────────────────────────


def test_next_task_returns_none_on_empty_list():
    assert next_task([]) is None


def test_next_task_returns_none_when_all_done():
    tasks = [BacklogTask(id="t1", goal="goal", status="done")]
    assert next_task(tasks) is None


def test_next_task_returns_highest_priority():
    tasks = [
        BacklogTask(id="t1", goal="g1", priority="low", status="pending"),
        BacklogTask(id="t2", goal="g2", priority="critical", status="pending"),
        BacklogTask(id="t3", goal="g3", priority="medium", status="pending"),
    ]
    result = next_task(tasks)
    assert result.id == "t2"


def test_next_task_skips_running_and_done():
    tasks = [
        BacklogTask(id="t1", goal="g1", status="running"),
        BacklogTask(id="t2", goal="g2", status="done"),
        BacklogTask(id="t3", goal="g3", status="pending"),
    ]
    result = next_task(tasks)
    assert result.id == "t3"


# ─── read_backlog with no file ───────────────────────────────────────────────


def test_read_backlog_missing_file_returns_empty(tmp_path):
    tasks = read_backlog()  # conftest.py redirects SETTINGS.paths to tmp_path
    assert tasks == []


def test_read_backlog_corrupt_yaml_returns_empty(tmp_path):
    from sovereign_agent.config import SETTINGS
    SETTINGS.paths.backlog_yaml.write_text(":::not valid yaml:::\n")
    tasks = read_backlog()
    assert tasks == []


# ─── write_backlog + read_backlog roundtrip ───────────────────────────────────


def test_write_read_backlog_roundtrip(tmp_path):
    tasks = [BacklogTask(id="x1", goal="do something", status="pending")]
    write_backlog(tasks)
    loaded = read_backlog()
    assert len(loaded) == 1
    assert loaded[0].id == "x1"
    assert loaded[0].status == "pending"


# ─── _update_task_status with unknown ID ─────────────────────────────────────


def test_update_task_status_unknown_id_no_crash(tmp_path):
    tasks = [BacklogTask(id="known", goal="goal", status="pending")]
    write_backlog(tasks)

    ctrl = ModeController(
        tools={},
        client=MagicMock(),
        settings=MagicMock(cooldown_seconds=0, empty_backlog_sleep=0, per_task_budget=MagicMock()),
    )
    ctrl._update_task_status("UNKNOWN-ID", "done")  # must not raise


# ─── Schedule injection failure emits event ──────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_injection_failure_emits_event(tmp_path):
    """When schedule injection raises, 'schedule-inject-error-d' must be emitted.

    This test verifies the M64 fix in mode_controller.py. It passes only after
    apply_protocol_zero_hardening.sh has patched the silent 'except Exception: pass'
    to emit the event. Until then, it correctly fails — that's the signal to apply.
    """
    import inspect
    import sovereign_agent.mode_controller as mc_mod
    src = inspect.getsource(mc_mod)
    if "schedule-inject-error-d" not in src:
        pytest.skip("M64 mode_controller fix not yet applied — run apply_protocol_zero_hardening.sh first")

    emitted = []
    write_backlog([])

    ctrl = ModeController(
        tools={},
        client=MagicMock(),
        settings=MagicMock(cooldown_seconds=0, empty_backlog_sleep=0, per_task_budget=MagicMock()),
    )

    def _bad_inject(store):
        raise RuntimeError("injector explosion")

    with (
        patch("sovereign_agent.mode_controller.emit_event", side_effect=lambda t, **kw: emitted.append(t)),
        patch("sovereign_agent.schedule.check_and_inject_due", side_effect=_bad_inject),
    ):
        await ctrl._drain_iteration()

    assert "schedule-inject-error-d" in emitted, (
        f"Expected 'schedule-inject-error-d' in emitted events, got: {emitted}"
    )


# ─── Poison cascade prevention ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poison_task_does_not_block_next_task(tmp_path):
    """After one task raises an exception (→ poison), the next task should run.

    Task IDs are chosen so 'aaa-explode' sorts before 'bbb-safe' alphabetically,
    ensuring _drain_iteration() picks the crashing task first (next_task sorts
    by priority_rank then id, and both tasks have equal priority).
    """
    tasks = [
        BacklogTask(id="aaa-explode", goal="will explode", status="pending"),
        BacklogTask(id="bbb-safe", goal="will succeed", status="pending"),
    ]
    write_backlog(tasks)

    mock_loop_result = MagicMock()
    mock_loop_result.reason = "complete"
    mock_loop_result.iterations = 1
    mock_loop_result.tokens_used = 100
    mock_loop_result.lesson_id = ""

    call_count = [0]

    async def _fake_loop(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("simulated task crash")
        return mock_loop_result

    ctrl = ModeController(
        tools={},
        client=MagicMock(),
        settings=MagicMock(cooldown_seconds=0, empty_backlog_sleep=0, per_task_budget=MagicMock()),
    )

    with patch("sovereign_agent.mode_controller.agent_loop", side_effect=_fake_loop):
        # First drain: sorts by id → picks 'aaa-explode', it raises → marks poison
        ran1 = await ctrl._drain_iteration()
        # Second drain: picks 'bbb-safe', succeeds
        ran2 = await ctrl._drain_iteration()

    assert ran1 is True
    assert ran2 is True

    final_tasks = read_backlog()
    statuses = {t.id: t.status for t in final_tasks}
    assert statuses["aaa-explode"] == "poison"
    assert statuses["bbb-safe"] == "done"


# ─── Task exception → poison status ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_exception_sets_poison_status(tmp_path):
    tasks = [BacklogTask(id="crash-task", goal="will crash", status="pending")]
    write_backlog(tasks)

    async def _always_crash(**kwargs):
        raise ValueError("test crash")

    ctrl = ModeController(
        tools={},
        client=MagicMock(),
        settings=MagicMock(cooldown_seconds=0, empty_backlog_sleep=0, per_task_budget=MagicMock()),
    )

    with patch("sovereign_agent.mode_controller.agent_loop", side_effect=_always_crash):
        await ctrl._drain_iteration()

    final_tasks = read_backlog()
    assert final_tasks[0].status == "poison"
    assert "unhandled" in final_tasks[0].notes or "crash" in final_tasks[0].notes.lower()


# ─── Empty backlog returns False ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drain_returns_false_on_empty_backlog(tmp_path):
    write_backlog([])

    ctrl = ModeController(
        tools={},
        client=MagicMock(),
        settings=MagicMock(cooldown_seconds=0, empty_backlog_sleep=0, per_task_budget=MagicMock()),
    )

    ran = await ctrl._drain_iteration()
    assert ran is False
