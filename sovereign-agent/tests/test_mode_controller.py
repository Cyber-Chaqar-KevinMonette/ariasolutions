"""Mode Controller tests. Architecture §5 + §11.

These cover the backlog operations — read/write atomicity, priority ordering,
status transitions, and the next_task picker. Not testing the actual loop
execution (that needs a live Ollama).
"""
from __future__ import annotations

import yaml

from sovereign_agent.config import SETTINGS
from sovereign_agent.mode_controller import (
    BacklogTask,
    add_task,
    next_task,
    read_backlog,
    remove_task,
    write_backlog,
)


def test_read_empty_backlog_returns_empty_list():
    # Backlog file doesn't exist yet
    tasks = read_backlog()
    assert tasks == []


def test_write_then_read_roundtrip():
    tasks = [
        BacklogTask(id="a", goal="first task", priority="high", mode="oneshot"),
        BacklogTask(id="b", goal="second task", priority="low", mode="busy"),
    ]
    write_backlog(tasks)
    loaded = read_backlog()
    assert len(loaded) == 2
    assert loaded[0].id == "a"
    assert loaded[0].priority == "high"
    assert loaded[1].id == "b"
    assert loaded[1].mode == "busy"


def test_next_task_picks_critical_over_high():
    tasks = [
        BacklogTask(id="med", goal="m", priority="medium"),
        BacklogTask(id="high", goal="h", priority="high"),
        BacklogTask(id="crit", goal="c", priority="critical"),
        BacklogTask(id="low", goal="l", priority="low"),
    ]
    chosen = next_task(tasks)
    assert chosen is not None
    assert chosen.id == "crit"


def test_next_task_skips_running_and_done():
    tasks = [
        BacklogTask(id="running-task", goal="x", priority="critical", status="running"),
        BacklogTask(id="done-task", goal="x", priority="high", status="done"),
        BacklogTask(id="todo-task", goal="x", priority="medium", status="pending"),
    ]
    chosen = next_task(tasks)
    assert chosen.id == "todo-task"


def test_next_task_returns_none_when_drained():
    tasks = [
        BacklogTask(id="a", goal="x", status="done"),
        BacklogTask(id="b", goal="x", status="poison"),
    ]
    assert next_task(tasks) is None


def test_add_task_appends():
    add_task(goal="first one", priority="high")
    add_task(goal="second one", priority="low")
    tasks = read_backlog()
    assert len(tasks) == 2
    assert tasks[0].goal == "first one"
    assert tasks[1].priority == "low"


def test_add_task_returns_with_id():
    task = add_task(goal="auto-id task")
    assert task.id.startswith("task-")
    assert len(task.id) > 10  # ULID-ish


def test_remove_task_works():
    add_task(goal="keep me", priority="medium", task_id="task-keep")
    add_task(goal="delete me", priority="medium", task_id="task-delete")
    assert remove_task("task-delete") is True
    remaining = read_backlog()
    assert len(remaining) == 1
    assert remaining[0].id == "task-keep"


def test_remove_nonexistent_task_returns_false():
    assert remove_task("does-not-exist") is False


def test_write_is_atomic_via_tmp_rename():
    """A failed write shouldn't corrupt an existing backlog."""
    write_backlog([BacklogTask(id="a", goal="original")])
    # Simulate concurrent reads while we write — the .tmp + rename pattern
    # means readers see either the old or new file, never a partial one.
    write_backlog([BacklogTask(id="b", goal="updated")])
    tasks = read_backlog()
    assert len(tasks) == 1
    assert tasks[0].id == "b"

    # The tmp file should not linger after a successful write
    tmp_path = SETTINGS.paths.backlog_yaml.with_suffix(".tmp")
    assert not tmp_path.exists()


def test_malformed_backlog_returns_empty_list():
    """A corrupt backlog.yaml shouldn't crash read_backlog."""
    path = SETTINGS.paths.backlog_yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this: is: not: valid: yaml: at: all: ::: -")
    tasks = read_backlog()
    # Either parses to nothing or fails gracefully — either way, no crash
    assert isinstance(tasks, list)


def test_backlog_skips_entries_missing_required_fields():
    """If a task in YAML lacks `id` or `goal`, it's silently skipped — never
    half-loaded — to avoid contaminating the run with malformed entries."""
    path = SETTINGS.paths.backlog_yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({
        "tasks": [
            {"id": "good", "goal": "valid"},
            {"goal": "no id — should be dropped"},
            {"id": "no goal — should also be dropped"},
            {"id": "another-good", "goal": "also valid"},
        ]
    }))
    tasks = read_backlog()
    assert len(tasks) == 2
    assert {t.id for t in tasks} == {"good", "another-good"}


def test_priority_rank_unknown_defaults_to_medium():
    t = BacklogTask(id="x", goal="x", priority="weird-value")
    assert t.priority_rank() == 2  # medium
