"""Tests for continuation.py — replayable task state (M81).

Covers: format_elapsed edge cases, Continuation property correctness
(cursor, progress, model affinity, elapsed, is_drained), status
recomputation (update_status_from_steps), YAML roundtrip, ContinuationStore
create/get/lock/delete, concurrent lock exclusion, and corrupt-input rejection.

No mocking of business logic — tests drive real code against tmp_path.
"""
from __future__ import annotations

import fcntl
import os
import threading
import time
from pathlib import Path

import pytest
import yaml

from sovereign_agent.continuation import (
    Continuation,
    ContinuationCorrupt,
    ContinuationLocked,
    ContinuationNotFound,
    ContinuationStore,
    Step,
    _from_yaml_dict,
    _to_yaml_dict,
    format_elapsed,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _step(
    id: int = 0,
    kind: str = "test",
    status: str = "pending",
    required_model: str = "orchestrator",
    elapsed_seconds: float | None = None,
) -> Step:
    return Step(
        id=id,
        kind=kind,
        status=status,  # type: ignore[arg-type]
        required_model=required_model,
        elapsed_seconds=elapsed_seconds,
    )


def _make_cont(steps: list[Step], status: str = "in_progress") -> Continuation:
    return Continuation(
        task_id="test-task-001",
        goal="test goal",
        planner="test-planner",
        steps=steps,
        status=status,  # type: ignore[arg-type]
    )


# ── format_elapsed ─────────────────────────────────────────────────────────────


def test_format_elapsed_none():
    assert format_elapsed(None) == "—"


def test_format_elapsed_subsecond():
    assert format_elapsed(0.42) == "0.42s"


def test_format_elapsed_seconds():
    assert format_elapsed(12.7) == "12.70s"


def test_format_elapsed_minutes():
    result = format_elapsed(90)
    assert result == "1m 30s"


def test_format_elapsed_hours():
    result = format_elapsed(3725)
    assert result == "1h 2m 5s"


# ── Continuation properties ────────────────────────────────────────────────────


def test_cursor_empty_steps():
    cont = _make_cont([])
    assert cont.cursor == 0


def test_cursor_all_done():
    steps = [_step(i, status="done") for i in range(3)]
    cont = _make_cont(steps)
    assert cont.cursor == 3  # len(steps), no pending


def test_cursor_pending_in_middle():
    steps = [
        _step(0, status="done"),
        _step(1, status="pending"),
        _step(2, status="pending"),
    ]
    cont = _make_cont(steps)
    assert cont.cursor == 1


def test_progress_empty():
    cont = _make_cont([])
    done, total = cont.progress
    assert done == 0 and total == 0


def test_progress_partial():
    steps = [
        _step(0, status="done"),
        _step(1, status="pending"),
        _step(2, status="poisoned"),
    ]
    cont = _make_cont(steps)
    done, total = cont.progress
    assert done == 2 and total == 3  # done + poisoned both count


def test_next_pending_returns_none_when_drained():
    steps = [_step(i, status="done") for i in range(2)]
    cont = _make_cont(steps)
    assert cont.next_pending() is None


def test_next_pending_for_model_filters_correctly():
    steps = [
        _step(0, status="pending", required_model="orchestrator"),
        _step(1, status="pending", required_model="vision"),
        _step(2, status="pending", required_model="orchestrator"),
    ]
    cont = _make_cont(steps)
    result = cont.next_pending_for_model("vision")
    assert result is not None and result.id == 1


def test_models_needed_orchestrator_first():
    steps = [
        _step(0, status="pending", required_model="vision"),
        _step(1, status="pending", required_model="orchestrator"),
        _step(2, status="pending", required_model="coder"),
    ]
    cont = _make_cont(steps)
    models = cont.models_needed()
    assert models[0] == "orchestrator"
    assert set(models) == {"orchestrator", "vision", "coder"}


def test_models_needed_empty_when_drained():
    steps = [_step(i, status="done") for i in range(3)]
    cont = _make_cont(steps)
    assert cont.models_needed() == []


def test_progress_by_model():
    steps = [
        _step(0, status="done", required_model="orchestrator"),
        _step(1, status="pending", required_model="orchestrator"),
        _step(2, status="done", required_model="vision"),
    ]
    cont = _make_cont(steps)
    by_model = cont.progress_by_model()
    assert by_model["orchestrator"] == (1, 2)
    assert by_model["vision"] == (1, 1)


def test_total_elapsed_seconds_handles_none():
    steps = [
        _step(0, status="done", elapsed_seconds=10.5),
        _step(1, status="done", elapsed_seconds=None),
        _step(2, status="done", elapsed_seconds=20.0),
    ]
    cont = _make_cont(steps)
    assert abs(cont.total_elapsed_seconds - 30.5) < 0.001


def test_is_drained_false_with_pending():
    steps = [_step(0, status="done"), _step(1, status="pending")]
    assert not _make_cont(steps).is_drained()


def test_is_drained_true_all_terminal():
    steps = [
        _step(0, status="done"),
        _step(1, status="poisoned"),
        _step(2, status="skipped"),
    ]
    assert _make_cont(steps).is_drained()


# ── update_status_from_steps ───────────────────────────────────────────────────


def test_update_status_empty_steps_gives_planned():
    cont = _make_cont([], status="in_progress")
    cont.update_status_from_steps()
    assert cont.status == "planned"


def test_update_status_done_when_all_succeeded():
    steps = [_step(i, status="done") for i in range(3)]
    cont = _make_cont(steps, status="in_progress")
    cont.update_status_from_steps()
    assert cont.status == "done"


def test_update_status_poisoned_when_any_poisoned():
    steps = [_step(0, status="done"), _step(1, status="poisoned")]
    cont = _make_cont(steps, status="in_progress")
    cont.update_status_from_steps()
    assert cont.status == "poisoned"


def test_update_status_preserves_paused_with_pending():
    steps = [_step(0, status="done"), _step(1, status="pending")]
    cont = _make_cont(steps, status="paused")
    cont.update_status_from_steps()
    assert cont.status == "paused"


def test_update_status_paused_settles_to_done_when_drained():
    steps = [_step(i, status="done") for i in range(2)]
    cont = _make_cont(steps, status="paused")
    cont.update_status_from_steps()
    assert cont.status == "done"


# ── YAML roundtrip ─────────────────────────────────────────────────────────────


def test_yaml_roundtrip_preserves_all_fields():
    steps = [
        _step(0, status="done", elapsed_seconds=5.5, required_model="coder"),
        _step(1, status="pending", required_model="vision"),
    ]
    original = Continuation(
        task_id="roundtrip-001",
        goal="roundtrip goal",
        planner="test-planner",
        planner_args={"key": "value"},
        steps=steps,
        status="in_progress",
        output_path="/tmp/out.txt",
        notes="test notes",
    )
    d = _to_yaml_dict(original)
    restored = _from_yaml_dict(d)

    assert restored.task_id == "roundtrip-001"
    assert restored.goal == "roundtrip goal"
    assert restored.planner_args == {"key": "value"}
    assert len(restored.steps) == 2
    assert restored.steps[0].status == "done"
    assert restored.steps[0].elapsed_seconds == 5.5
    assert restored.steps[1].required_model == "vision"
    assert restored.output_path == "/tmp/out.txt"
    assert restored.notes == "test notes"


def test_from_yaml_dict_missing_required_fields_raises():
    with pytest.raises(ContinuationCorrupt, match="missing required field"):
        _from_yaml_dict({"task_id": "x", "goal": "g"})  # missing 'planner'


def test_from_yaml_dict_invalid_status_raises():
    with pytest.raises(ContinuationCorrupt, match="invalid status"):
        _from_yaml_dict({"task_id": "x", "goal": "g", "planner": "p", "status": "flying"})


def test_from_yaml_dict_invalid_step_status_raises():
    with pytest.raises(ContinuationCorrupt, match="invalid status"):
        _from_yaml_dict({
            "task_id": "x", "goal": "g", "planner": "p",
            "steps": [{"id": 0, "kind": "test", "status": "flying"}],
        })


def test_from_yaml_dict_steps_not_list_raises():
    with pytest.raises(ContinuationCorrupt, match="'steps' must be a list"):
        _from_yaml_dict({"task_id": "x", "goal": "g", "planner": "p", "steps": "bad"})


# ── ContinuationStore ─────────────────────────────────────────────────────────


def test_store_create_and_get_roundtrip(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    steps = [_step(0), _step(1)]
    cont = store.create(
        goal="test goal",
        planner="test-planner",
        planner_args={"x": 1},
        steps=steps,
        output_path="/tmp/out.txt",
    )
    retrieved = store.get(cont.task_id)
    assert retrieved.goal == "test goal"
    assert retrieved.planner_args == {"x": 1}
    assert retrieved.output_path == "/tmp/out.txt"
    assert len(retrieved.steps) == 2


def test_store_get_not_found_raises(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    with pytest.raises(ContinuationNotFound):
        store.get("nonexistent-id")


def test_store_get_corrupt_yaml_raises(tmp_path):
    root = tmp_path / "conts"
    root.mkdir()
    bad_file = root / "bad-task.yaml"
    bad_file.write_text("{{invalid: yaml: :\n")
    store = ContinuationStore(root)
    with pytest.raises(ContinuationCorrupt):
        store.get("bad-task")


def test_store_list_ids_sorted(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    ids = []
    for _ in range(3):
        cont = store.create(goal="g", planner="p", planner_args={}, steps=[_step(0)])
        ids.append(cont.task_id)
    listed = store.list_ids()
    assert listed == sorted(ids)


def test_store_lock_persists_mutation(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    cont = store.create(goal="g", planner="p", planner_args={}, steps=[_step(0)])
    with store.lock(cont.task_id) as c:
        c.notes = "mutated"
    assert store.get(cont.task_id).notes == "mutated"


def test_store_lock_no_write_on_exception(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    cont = store.create(goal="g", planner="p", planner_args={}, steps=[_step(0)])
    try:
        with store.lock(cont.task_id) as c:
            c.notes = "should-not-persist"
            raise RuntimeError("deliberate exception")
    except RuntimeError:
        pass
    assert store.get(cont.task_id).notes == ""


def test_store_concurrent_lock_raises_continuation_locked(tmp_path):
    """Non-blocking second lock on same task → ContinuationLocked."""
    store = ContinuationStore(tmp_path / "conts")
    cont = store.create(goal="g", planner="p", planner_args={}, steps=[_step(0)])

    lock_path = store._lock_path(cont.task_id)
    # Simulate a held lock by acquiring it in this thread
    lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Now try to acquire via the store — should raise
        with pytest.raises(ContinuationLocked):
            with store.lock(cont.task_id, blocking=False):
                pass  # should not reach here
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def test_store_delete_removes_files(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    cont = store.create(goal="g", planner="p", planner_args={}, steps=[_step(0)])
    assert store.delete(cont.task_id) is True
    with pytest.raises(ContinuationNotFound):
        store.get(cont.task_id)


def test_store_delete_nonexistent_returns_false(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    store.ensure_root()
    assert store.delete("nonexistent-task") is False


def test_store_list_all_status_filter(tmp_path):
    store = ContinuationStore(tmp_path / "conts")
    c1 = store.create(goal="a", planner="p", planner_args={}, steps=[_step(0)])
    c2 = store.create(goal="b", planner="p", planner_args={}, steps=[])  # no steps → done
    with store.lock(c1.task_id) as c:
        c.status = "poisoned"
    done_list = store.list_all(status="done")
    assert any(c.task_id == c2.task_id for c in done_list)
    assert all(c.task_id != c1.task_id for c in done_list)
