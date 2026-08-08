"""
╔══════════════════════════════════════════════════════════════════════════╗
║  mode_controller.py — Long-running orchestration                         ║
║  Architecture §5 + §11                                                   ║
╚══════════════════════════════════════════════════════════════════════════╝

While ``loop.py`` runs ONE task to completion, ``ModeController`` runs the
agent CONTINUOUSLY — pulling tasks from a backlog, handling poison/halt/
budget exits, and keeping the system productive across hours and days.

Modes it supports:

  ◊ BUSY     — drain the backlog forever; sleep briefly when empty
  ◊ TIMED    — run between t1 and t2; halt cleanly outside the window
  ◊ UNTIL    — run until a stop predicate is satisfied

Each mode wraps ``agent_loop`` and adds the meta-orchestration layer:
  - read backlog.yaml
  - pop highest-priority task
  - run loop
  - on settle/poison/budget: emit task-done-d, mark in backlog, continue
  - on halted: respect PROTOCOL-ZERO and exit cleanly
  - cooldown between tasks (configurable, default 5s) — keeps thermals sane

The backlog format (YAML, edited by user OR by the agent itself):

    tasks:
      - id: task-001
        priority: high
        goal: "Summarize all .md files in ~/notes and write atoms"
        mode: busy
      - id: task-002
        priority: medium
        goal: "Catalog repo at ~/projects/foo"
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

from . import protocol_zero
from .config import SETTINGS
from .events import emit_event, force_fsync
from .loop import LoopResult, agent_loop
from .modes import Mode, RunBudget
from .ollama_client import OllamaClient
from .tools.base import Tool


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class BacklogTask:
    """One task entry from backlog.yaml."""

    id: str
    goal: str
    priority: str = "medium"
    mode: str = "oneshot"      # the mode to run THIS task under
    status: str = "pending"    # pending | running | done | poison | budget | halted
    notes: str = ""

    def priority_rank(self) -> int:
        return PRIORITY_ORDER.get(self.priority.lower(), 2)


def read_backlog() -> list[BacklogTask]:
    """Load backlog.yaml. Returns empty list if missing."""
    path = SETTINGS.paths.backlog_yaml
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return []
    raw_tasks = data.get("tasks") or []
    return [
        BacklogTask(
            id=str(t.get("id", "")),
            goal=str(t.get("goal", "")),
            priority=str(t.get("priority", "medium")),
            mode=str(t.get("mode", "oneshot")),
            status=str(t.get("status", "pending")),
            notes=str(t.get("notes", "")),
        )
        for t in raw_tasks
        if t.get("id") and t.get("goal")
    ]


def write_backlog(tasks: list[BacklogTask]) -> None:
    """Persist backlog atomically."""
    path = SETTINGS.paths.backlog_yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tasks": [
            {
                "id": t.id,
                "goal": t.goal,
                "priority": t.priority,
                "mode": t.mode,
                "status": t.status,
                "notes": t.notes,
            }
            for t in tasks
        ]
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False))
    tmp.replace(path)


def next_task(tasks: list[BacklogTask]) -> BacklogTask | None:
    """Pick the highest-priority pending task. None if backlog is drained."""
    pending = [t for t in tasks if t.status == "pending"]
    if not pending:
        return None
    pending.sort(key=lambda t: (t.priority_rank(), t.id))
    return pending[0]


@dataclass
class ControllerSettings:
    """Tunables for the long-running modes."""

    cooldown_seconds: float = 5.0           # between tasks
    empty_backlog_sleep: float = 30.0       # when no work pending
    per_task_budget: RunBudget = None       # None = use defaults

    def __post_init__(self) -> None:
        if self.per_task_budget is None:
            self.per_task_budget = RunBudget()


class ModeController:
    """Long-running task orchestrator.

    Usage:
        controller = ModeController(tools=tools_dict)
        await controller.run_busy()                    # drain forever
        await controller.run_until(lambda: <pred>)     # run until predicate
        await controller.run_timed(start_ts, end_ts)   # run within window
    """

    def __init__(
        self,
        *,
        tools: dict[str, Tool],
        client: OllamaClient | None = None,
        settings: ControllerSettings | None = None,
    ) -> None:
        self.tools = tools
        self.client = client or OllamaClient()
        self.cfg = settings or ControllerSettings()
        protocol_zero.install_signal_handlers()

    async def _run_one_task(self, task: BacklogTask) -> LoopResult:
        try:
            mode = Mode(task.mode.lower())
        except ValueError:
            mode = Mode.ONESHOT

        emit_event(
            "task-start-d",
            plane="control",
            trace_id="controller",
            payload={"task_id": task.id, "mode": mode.value, "priority": task.priority},
        )

        result = await agent_loop(
            goal=task.goal,
            mode=mode,
            budget=self.cfg.per_task_budget,
            tools=self.tools,
            client=self.client,
        )

        emit_event(
            "task-end-d",
            plane="control",
            trace_id="controller",
            payload={
                "task_id": task.id,
                "outcome": result.reason,
                "iterations": result.iterations,
                "tokens": result.tokens_used,
                "lesson_id": result.lesson_id,
            },
        )
        return result

    def _update_task_status(self, task_id: str, status: str, note: str = "") -> None:
        tasks = read_backlog()
        for t in tasks:
            if t.id == task_id:
                t.status = status
                if note:
                    t.notes = note
                break
        write_backlog(tasks)

    async def _drain_iteration(self) -> bool:
        """Run one task from the backlog. Returns True if a task ran."""
        if protocol_zero.is_armed():
            emit_event(
                "controller-halt-d",
                plane="control",
                trace_id="controller",
                payload={"reason": "protocol_zero"},
            )
            return False

        # cron-internal: check scheduled entries, inject due tasks
        try:
            from sovereign_agent.schedule import ScheduleStore, check_and_inject_due, _schedule_path
            check_and_inject_due(ScheduleStore(_schedule_path()))  # cron-internal-drain-d
        except Exception as _sched_err:  # noqa: BLE001
            emit_event(
                "schedule-inject-error-d",
                plane="control",
                trace_id="controller",
                payload={"error": str(_sched_err)},
            )

        tasks = read_backlog()
        task = next_task(tasks)
        if task is None:
            return False

        self._update_task_status(task.id, "running")
        try:
            result = await self._run_one_task(task)
            terminal_status = {
                "complete": "done",
                "budget":   "budget",
                "poison":   "poison",
                "halted":   "halted",
            }.get(result.reason or "", "done")
            self._update_task_status(
                task.id,
                terminal_status,
                note=f"iters={result.iterations} tokens={result.tokens_used}",
            )
        except Exception as e:  # noqa: BLE001
            self._update_task_status(task.id, "poison", note=f"unhandled: {e}")
            emit_event(
                "controller-task-x",
                plane="control",
                trace_id="controller",
                payload={"task_id": task.id, "error": str(e)[:500]},
            )
            return True

        return True

    async def run_busy(self) -> None:
        """BUSY mode — drain the backlog forever until PROTOCOL-ZERO."""
        emit_event(
            "controller-d",
            plane="control",
            trace_id="controller",
            payload={"mode": "busy", "started_at": time.time()},
        )
        try:
            while not protocol_zero.is_armed():
                ran = await self._drain_iteration()
                if ran:
                    await asyncio.sleep(self.cfg.cooldown_seconds)
                else:
                    await asyncio.sleep(self.cfg.empty_backlog_sleep)
        finally:
            force_fsync()
            emit_event(
                "controller-stop-d",
                plane="control",
                trace_id="controller",
                payload={"mode": "busy", "stopped_at": time.time()},
            )

    async def run_until(
        self, predicate: Callable[[], Awaitable[bool] | bool]
    ) -> None:
        """UNTIL mode — drain the backlog until ``predicate()`` returns True."""
        emit_event(
            "controller-d",
            plane="control",
            trace_id="controller",
            payload={"mode": "until", "started_at": time.time()},
        )
        try:
            while not protocol_zero.is_armed():
                pred_result = predicate()
                if asyncio.iscoroutine(pred_result):
                    done = await pred_result
                else:
                    done = bool(pred_result)
                if done:
                    break
                ran = await self._drain_iteration()
                await asyncio.sleep(
                    self.cfg.cooldown_seconds if ran else self.cfg.empty_backlog_sleep
                )
        finally:
            force_fsync()
            emit_event(
                "controller-stop-d",
                plane="control",
                trace_id="controller",
                payload={"mode": "until", "stopped_at": time.time()},
            )

    async def run_timed(self, start_ts: float, end_ts: float) -> None:
        """TIMED mode — work between ``start_ts`` and ``end_ts`` (epoch seconds)."""
        # Sleep until the window starts
        now = time.time()
        if now < start_ts:
            await asyncio.sleep(start_ts - now)

        emit_event(
            "controller-d",
            plane="control",
            trace_id="controller",
            payload={"mode": "timed", "start_ts": start_ts, "end_ts": end_ts},
        )
        try:
            while time.time() < end_ts and not protocol_zero.is_armed():
                ran = await self._drain_iteration()
                await asyncio.sleep(
                    self.cfg.cooldown_seconds if ran else self.cfg.empty_backlog_sleep
                )
        finally:
            force_fsync()
            emit_event(
                "controller-stop-d",
                plane="control",
                trace_id="controller",
                payload={"mode": "timed", "stopped_at": time.time()},
            )


# ─── Backlog helpers (used by CLI) ──────────────────────────────────────────


def add_task(
    *, goal: str, priority: str = "medium", mode: str = "oneshot", task_id: str | None = None
) -> BacklogTask:
    """Append a new task to backlog.yaml. Returns the task."""
    from ulid import ULID

    tasks = read_backlog()
    new = BacklogTask(
        id=task_id or f"task-{ULID()}",
        goal=goal,
        priority=priority,
        mode=mode,
    )
    tasks.append(new)
    write_backlog(tasks)
    return new


def remove_task(task_id: str) -> bool:
    tasks = read_backlog()
    before = len(tasks)
    tasks = [t for t in tasks if t.id != task_id]
    write_backlog(tasks)
    return len(tasks) < before
