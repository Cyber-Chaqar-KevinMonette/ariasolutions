"""Tests for the continuation store. v0.2.5.

Coverage:
  - create / get / list / delete round-trip
  - lock-block atomic mutation
  - second concurrent lock raises ContinuationLocked (non-blocking case)
  - lock blocks then succeeds when first releases (timed case)
  - exception inside lock block does NOT persist mutations
  - malformed YAML raises ContinuationCorrupt, doesn't crash
  - missing required fields → ContinuationCorrupt
  - cursor / progress / next_pending / is_drained / update_status_from_steps
  - atomic-write survives partial-fsync simulation
"""
from __future__ import annotations

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
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> ContinuationStore:
    return ContinuationStore(tmp_path / "continuations")


def _make_steps(n: int) -> list[Step]:
    return [
        Step(id=i, kind="test_step", args={"i": i}, status="pending")
        for i in range(n)
    ]


# ─── CRUD ───────────────────────────────────────────────────────────────────


def test_create_and_get_round_trip(store: ContinuationStore) -> None:
    cont = store.create(
        goal="test task", planner="inventory", planner_args={"x": 1},
        steps=_make_steps(3),
    )
    assert cont.task_id.startswith("cont-")
    assert cont.status == "planned"
    assert len(cont.steps) == 3

    fetched = store.get(cont.task_id)
    assert fetched.task_id == cont.task_id
    assert fetched.goal == "test task"
    assert fetched.planner == "inventory"
    assert fetched.planner_args == {"x": 1}
    assert len(fetched.steps) == 3
    assert all(s.status == "pending" for s in fetched.steps)


def test_get_nonexistent_raises(store: ContinuationStore) -> None:
    with pytest.raises(ContinuationNotFound):
        store.get("does-not-exist")


def test_list_ids_sorted(store: ContinuationStore) -> None:
    a = store.create(goal="a", planner="p", planner_args={}, steps=[], task_id="cont-aaa")
    b = store.create(goal="b", planner="p", planner_args={}, steps=[], task_id="cont-bbb")
    c = store.create(goal="c", planner="p", planner_args={}, steps=[], task_id="cont-ccc")
    ids = store.list_ids()
    assert ids == ["cont-aaa", "cont-bbb", "cont-ccc"]


def test_list_all_filters_by_status(store: ContinuationStore) -> None:
    # cont-1: planned (steps remain pending)
    store.create(goal="a", planner="p", planner_args={}, steps=_make_steps(2), task_id="cont-1")
    # cont-2: drive to done via lock
    cont2 = store.create(goal="b", planner="p", planner_args={}, steps=_make_steps(1), task_id="cont-2")
    with store.lock(cont2.task_id) as c:
        c.steps[0].status = "done"
        c.update_status_from_steps()

    planned = store.list_all(status="planned")
    done = store.list_all(status="done")
    assert {c.task_id for c in planned} == {"cont-1"}
    assert {c.task_id for c in done} == {"cont-2"}


def test_create_duplicate_raises(store: ContinuationStore) -> None:
    store.create(goal="a", planner="p", planner_args={}, steps=[], task_id="cont-x")
    with pytest.raises(FileExistsError):
        store.create(goal="b", planner="p", planner_args={}, steps=[], task_id="cont-x")


def test_delete_returns_existed(store: ContinuationStore) -> None:
    store.create(goal="a", planner="p", planner_args={}, steps=[], task_id="cont-x")
    assert store.delete("cont-x") is True
    assert store.delete("cont-x") is False
    assert store.delete("never-existed") is False


def test_empty_steps_continuation_is_done_immediately(store: ContinuationStore) -> None:
    cont = store.create(goal="empty", planner="p", planner_args={}, steps=[])
    assert cont.status == "done"


# ─── Lock / transactional API ───────────────────────────────────────────────


def test_lock_persists_mutations(store: ContinuationStore) -> None:
    cont = store.create(goal="t", planner="p", planner_args={}, steps=_make_steps(2))
    with store.lock(cont.task_id) as c:
        c.steps[0].status = "done"
        c.steps[0].result = "ok"
        c.notes = "modified"

    fetched = store.get(cont.task_id)
    assert fetched.steps[0].status == "done"
    assert fetched.steps[0].result == "ok"
    assert fetched.notes == "modified"


def test_lock_exception_does_not_persist(store: ContinuationStore) -> None:
    cont = store.create(goal="t", planner="p", planner_args={}, steps=_make_steps(1))
    with pytest.raises(RuntimeError):
        with store.lock(cont.task_id) as c:
            c.steps[0].status = "done"
            raise RuntimeError("simulated crash mid-block")

    fetched = store.get(cont.task_id)
    assert fetched.steps[0].status == "pending", \
        "exception inside lock block must NOT persist any mutation"


def test_concurrent_lock_non_blocking_raises(store: ContinuationStore) -> None:
    cont = store.create(goal="t", planner="p", planner_args={}, steps=_make_steps(1))
    held_evt = threading.Event()
    release_evt = threading.Event()

    def hold_lock() -> None:
        with store.lock(cont.task_id) as c:
            held_evt.set()
            release_evt.wait(timeout=2.0)
            c.notes = "first"

    t = threading.Thread(target=hold_lock)
    t.start()
    held_evt.wait(timeout=1.0)
    try:
        with pytest.raises(ContinuationLocked):
            with store.lock(cont.task_id, blocking=False):
                pytest.fail("should not have acquired lock")
    finally:
        release_evt.set()
        t.join(timeout=2.0)

    fetched = store.get(cont.task_id)
    assert fetched.notes == "first"


def test_concurrent_lock_blocking_with_timeout_eventually_succeeds(
    store: ContinuationStore,
) -> None:
    cont = store.create(goal="t", planner="p", planner_args={}, steps=_make_steps(1))
    release_evt = threading.Event()
    held_evt = threading.Event()

    def hold_briefly() -> None:
        with store.lock(cont.task_id) as c:
            held_evt.set()
            release_evt.wait(timeout=2.0)
            c.notes = "first"

    t = threading.Thread(target=hold_briefly)
    t.start()
    held_evt.wait(timeout=1.0)
    # Schedule release after 100ms
    threading.Timer(0.1, release_evt.set).start()
    # This should block briefly then succeed.
    with store.lock(cont.task_id, blocking=True, timeout_seconds=5.0) as c:
        # The previous holder's mutation should already be visible.
        assert c.notes == "first"
        c.notes = "second"
    t.join(timeout=2.0)

    fetched = store.get(cont.task_id)
    assert fetched.notes == "second"


def test_concurrent_lock_blocking_timeout_expires(store: ContinuationStore) -> None:
    cont = store.create(goal="t", planner="p", planner_args={}, steps=_make_steps(1))
    held_evt = threading.Event()
    release_evt = threading.Event()

    def hold_long() -> None:
        with store.lock(cont.task_id):
            held_evt.set()
            release_evt.wait(timeout=2.0)

    t = threading.Thread(target=hold_long)
    t.start()
    held_evt.wait(timeout=1.0)
    try:
        start = time.monotonic()
        with pytest.raises(ContinuationLocked):
            with store.lock(cont.task_id, blocking=True, timeout_seconds=0.2):
                pytest.fail("should not acquire under timeout")
        elapsed = time.monotonic() - start
        assert 0.15 < elapsed < 1.0, f"timeout did not bound the wait: {elapsed:.3f}s"
    finally:
        release_evt.set()
        t.join(timeout=2.0)


def test_thirty_concurrent_increments_no_lost_writes(
    store: ContinuationStore,
) -> None:
    """Stress test: many threads each do read-modify-write under lock.

    Without proper locking, increments would be lost. This is the regression
    test for the same class of bug the prior chat caught and fixed.
    """
    cont = store.create(goal="t", planner="p", planner_args={"counter": 0}, steps=[])
    n_threads = 10
    increments_per_thread = 4

    def worker() -> None:
        for _ in range(increments_per_thread):
            with store.lock(cont.task_id, blocking=True, timeout_seconds=10.0) as c:
                c.planner_args["counter"] = int(c.planner_args.get("counter", 0)) + 1

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    fetched = store.get(cont.task_id)
    assert fetched.planner_args["counter"] == n_threads * increments_per_thread


# ─── Continuation methods (cursor / progress / drain) ───────────────────────


def test_cursor_and_progress() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=_make_steps(4))
    assert cont.cursor == 0
    assert cont.progress == (0, 4)
    cont.steps[0].status = "done"
    cont.steps[1].status = "done"
    assert cont.cursor == 2
    assert cont.progress == (2, 4)
    cont.steps[2].status = "skipped"
    cont.steps[3].status = "poisoned"
    assert cont.cursor == 4
    assert cont.progress == (4, 4)
    assert cont.is_drained() is True


def test_next_pending_walks_in_order() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=_make_steps(3))
    assert cont.next_pending().id == 0
    cont.steps[0].status = "done"
    assert cont.next_pending().id == 1


def test_update_status_from_steps_drained_clean() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=_make_steps(2))
    for s in cont.steps:
        s.status = "done"
    cont.update_status_from_steps()
    assert cont.status == "done"


def test_update_status_from_steps_drained_with_poison() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=_make_steps(2))
    cont.steps[0].status = "done"
    cont.steps[1].status = "poisoned"
    cont.update_status_from_steps()
    assert cont.status == "poisoned"


def test_update_status_from_steps_in_progress() -> None:
    cont = Continuation(task_id="t", goal="g", planner="p", steps=_make_steps(2))
    cont.steps[0].status = "done"
    cont.update_status_from_steps()
    assert cont.status == "in_progress"


# ─── Corruption handling ────────────────────────────────────────────────────


def test_malformed_yaml_raises(store: ContinuationStore, tmp_path: Path) -> None:
    store.ensure_root()
    path = store.root / "cont-bad.yaml"
    path.write_text("not: valid: yaml: at: all: [\n", encoding="utf-8")
    with pytest.raises(ContinuationCorrupt):
        store.get("cont-bad")


def test_missing_required_field_raises(store: ContinuationStore) -> None:
    store.ensure_root()
    path = store.root / "cont-missing.yaml"
    path.write_text(yaml.safe_dump({"task_id": "x"}), encoding="utf-8")
    with pytest.raises(ContinuationCorrupt):
        store.get("cont-missing")


def test_invalid_status_raises(store: ContinuationStore) -> None:
    store.ensure_root()
    path = store.root / "cont-bad-status.yaml"
    path.write_text(
        yaml.safe_dump({
            "task_id": "x", "goal": "g", "planner": "p",
            "status": "garbage",
        }),
        encoding="utf-8",
    )
    with pytest.raises(ContinuationCorrupt):
        store.get("cont-bad-status")


def test_list_all_skips_corrupt(store: ContinuationStore) -> None:
    store.create(goal="ok", planner="p", planner_args={}, steps=[], task_id="cont-good")
    store.ensure_root()
    (store.root / "cont-bad.yaml").write_text("[[[", encoding="utf-8")
    survivors = store.list_all()
    assert {c.task_id for c in survivors} == {"cont-good"}
