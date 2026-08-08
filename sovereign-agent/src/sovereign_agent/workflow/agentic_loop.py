"""
╔══════════════════════════════════════════════════════════════════════════╗
║  workflow/agentic_loop.py — plan → act → check                            ║
║  v0.2.37 — skeleton drop                                                  ║
║                                                                           ║
║  The skeleton of Aria's agentic core. Goals come in, get decomposed     ║
║  into a task graph, executed step by step with tool dispatch, and      ║
║  outcomes are written back to project memory.                          ║
║                                                                           ║
║  The loop                                                                ║
║                                                                           ║
║    1. intake(goal, project_id)        — capture intent                  ║
║    2. plan(workflow_id)               — produce a task graph             ║
║    3. step(workflow_id)               — execute one task                ║
║    4. check(workflow_id)              — evaluate, decide next            ║
║    5. summarize(workflow_id)          — write durable outcome           ║
║                                                                           ║
║  Skeleton honesty                                                        ║
║                                                                           ║
║    This module wires the LOOP but does not yet wire the EXECUTION.     ║
║    Tool dispatch is pluggable: register a ToolHandler and the loop     ║
║    will call it. The default handler is a no-op that just marks tasks ║
║    done — useful for testing the loop's shape without side effects.   ║
║                                                                           ║
║    Real tool dispatch (shell, file I/O, LLM calls, MCP) wires in via  ║
║    register_tool_handler() in v0.2.38+. The skeleton needs to walk    ║
║    before the muscle attaches.                                         ║
║                                                                           ║
║  Authority discipline                                                   ║
║                                                                           ║
║    For any task whose action_kind requires R1+ scope (file writes,     ║
║    external commands), the handler MUST route through Aegis           ║
║    (lease-gated repair_execute or equivalent). The agentic loop itself ║
║    has no implicit authority; it's just orchestration.                ║
║                                                                           ║
║  Workflow state lives in the tasks table                               ║
║                                                                           ║
║    A workflow is a tree of tasks rooted at one "workflow task." The   ║
║    workflow's task_id IS the workflow_id. Subtasks form the plan.     ║
║    outcome_json holds the per-step result. This means we don't need   ║
║    a separate workflows table; we reuse the bones.                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from sovereign_agent.events import emit_event
from sovereign_agent.persistence.projects import ProjectsManager, Task

logger = logging.getLogger(__name__)


def _emit(
    flag: str,
    *,
    trace_id: str,
    parent_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Emit a workflow event without ever letting a logging failure escape.

    Observability must not become a failure mode: if the event log is
    unwritable for any reason, the workflow still runs. Returns the event
    ULID on success, ``None`` on failure (debug-logged).
    """
    try:
        return emit_event(flag, plane="control", trace_id=trace_id, parent_id=parent_id, payload=payload or {})
    except Exception as exc:  # noqa: BLE001 — never break the loop on a log write
        logger.debug("workflow event %s failed to emit: %r", flag, exc)
        return None


# ─── Plan shape ──────────────────────────────────────────────────────────


@dataclass
class PlanStep:
    """One step a workflow will take."""
    title: str
    description: str
    action_kind: str         # 'note' | 'shell' | 'file_write' | 'llm_call' | ...
    action_input: dict[str, Any] = field(default_factory=dict)
    estimated_seconds: int = 0


@dataclass
class StepOutcome:
    """The result of executing one PlanStep."""
    succeeded: bool
    summary: str
    artifacts: list[str] = field(default_factory=list)
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ─── Tool handler protocol ───────────────────────────────────────────────


ToolHandler = Callable[[Task], StepOutcome]
"""A function that takes a Task, performs its action, returns an outcome.

Handlers are registered per action_kind. The agentic loop looks up the
right handler when stepping. If no handler is registered for a kind,
the task is marked 'blocked' with an explanatory outcome.
"""


def default_noop_handler(task: Task) -> StepOutcome:
    """Default handler — marks the task done without side effects.

    Useful for testing the loop's shape. Replace with real handlers as
    you wire in tools.
    """
    from sovereign_agent.persistence.store import _iso_now
    now = _iso_now()
    return StepOutcome(
        succeeded=True,
        summary=f"no-op handler executed step '{task.title}'",
        started_at=now,
        completed_at=now,
    )


# ─── The loop ────────────────────────────────────────────────────────────


class AgenticLoop:
    """Plan → act → check, backed by the project task graph.

    Construct with a ProjectsManager. Register tool handlers as you build
    them. Drive the loop with intake → plan → step (repeatedly) →
    summarize.
    """

    def __init__(self, projects: ProjectsManager):
        self._projects = projects
        self._handlers: dict[str, ToolHandler] = {
            "note": default_noop_handler,  # 'note' is the baseline kind
        }

    # ─── Handler registration ───────────────────────────────────────────

    def register_tool_handler(
        self, action_kind: str, handler: ToolHandler
    ) -> None:
        self._handlers[action_kind] = handler

    def registered_kinds(self) -> list[str]:
        return sorted(self._handlers)

    # ─── 1. Intake — capture goal as a workflow root task ────────────────

    def intake(
        self,
        project_id: str,
        goal: str,
        description: str = "",
    ) -> str:
        """Record the goal as a root task in the project. Returns workflow_id
        (which is the task_id of the root)."""
        workflow_id = self._projects.add_task(
            project_id=project_id,
            title=f"workflow: {goal}",
            description=description,
        )
        return workflow_id

    # ─── 2. Plan — decompose into PlanSteps as child tasks ───────────────

    def write_plan(
        self,
        workflow_id: str,
        steps: list[PlanStep],
    ) -> list[str]:
        """Write a plan into the task graph. Returns the list of created
        task_ids in order. Replaces any prior plan steps (idempotent at
        the planning phase — call once you know the plan)."""
        root = self._projects.get_task(workflow_id)
        if root is None:
            raise ValueError(f"unknown workflow_id: {workflow_id}")

        step_task_ids: list[str] = []
        for i, step in enumerate(steps, start=1):
            step_task_id = self._projects.add_task(
                project_id=root.project_id,
                parent_task_id=workflow_id,
                title=step.title,
                description=json.dumps({
                    "description": step.description,
                    "action_kind": step.action_kind,
                    "action_input": step.action_input,
                    "estimated_seconds": step.estimated_seconds,
                }),
                ordinal=i,
            )
            step_task_ids.append(step_task_id)
        # Mark the workflow root as in_progress.
        self._projects.set_task_status(workflow_id, "in_progress")
        return step_task_ids

    def append_step(self, workflow_id: str, step: PlanStep) -> str:
        """Append a single new step to the end of an existing plan, in order.

        Used for dynamic plan expansion when a capability need is discovered
        mid-run. The appended step is an ordinary planned task and is subject
        to the same dispatch + handler gates as any other step — appending it
        does not pre-authorize its execution.
        """
        root = self._projects.get_task(workflow_id)
        if root is None:
            raise ValueError(f"unknown workflow_id: {workflow_id}")
        existing = self.plan_steps(workflow_id)
        next_ordinal = (max((t.ordinal for t in existing), default=0) + 1)
        return self._projects.add_task(
            project_id=root.project_id,
            parent_task_id=workflow_id,
            title=step.title,
            description=json.dumps({
                "description": step.description,
                "action_kind": step.action_kind,
                "action_input": step.action_input,
                "estimated_seconds": step.estimated_seconds,
            }),
            ordinal=next_ordinal,
        )

    def plan_steps(self, workflow_id: str) -> list[Task]:
        """Return the workflow's plan steps, in order."""
        root = self._projects.get_task(workflow_id)
        if root is None:
            return []
        return self._projects.list_tasks(
            project_id=root.project_id, parent_task_id=workflow_id,
        )

    # ─── 3. Step — execute the next planned step ─────────────────────────

    def next_planned_step(self, workflow_id: str) -> Optional[Task]:
        """Find the next step that's still 'planned'. Returns None when the
        workflow has no more planned steps (either done, blocked, or
        abandoned)."""
        for step in self.plan_steps(workflow_id):
            if step.status == "planned":
                return step
        return None

    def step(self, workflow_id: str) -> Optional[StepOutcome]:
        """Execute one planned step. Returns the StepOutcome, or None if
        no planned step remains."""
        step_task = self.next_planned_step(workflow_id)
        if step_task is None:
            return None

        # Parse the step's action_kind from its description blob.
        try:
            blob = json.loads(step_task.description)
            action_kind = blob.get("action_kind", "note")
        except json.JSONDecodeError:
            action_kind = "note"

        # Mark in_progress before calling the handler.
        self._projects.set_task_status(step_task.task_id, "in_progress")

        # Observability: a workflow's events are grouped under trace_id =
        # workflow_id (the root task id). Every handler — present, missing,
        # or raising — produces a start/end pair the live cockpit can tail.
        start_event = _emit(
            "workflow-step-start-d",
            trace_id=workflow_id,
            payload={
                "step_task_id": step_task.task_id,
                "title": step_task.title,
                "action_kind": action_kind,
            },
        )

        handler = self._handlers.get(action_kind)
        if handler is None:
            outcome = StepOutcome(
                succeeded=False,
                summary=f"no handler registered for action_kind={action_kind!r}",
                error="missing-handler",
            )
            self._projects.set_task_status(
                step_task.task_id, "blocked",
                outcome=outcome.__dict__,
            )
            _emit(
                "workflow-step-blocked-d",
                trace_id=workflow_id,
                parent_id=start_event,
                payload={"title": step_task.title, "error": "missing-handler",
                         "action_kind": action_kind},
            )
            return outcome

        try:
            outcome = handler(step_task)
        except Exception as e:
            logger.exception("handler for %s raised", action_kind)
            outcome = StepOutcome(
                succeeded=False,
                summary=f"handler raised {type(e).__name__}",
                error=str(e),
            )
            self._projects.set_task_status(
                step_task.task_id, "blocked",
                outcome=outcome.__dict__,
            )
            _emit(
                "workflow-step-blocked-d",
                trace_id=workflow_id,
                parent_id=start_event,
                payload={"title": step_task.title,
                         "error": f"{type(e).__name__}: {e}"[:300]},
            )
            return outcome

        final_status = "done" if outcome.succeeded else "blocked"
        self._projects.set_task_status(
            step_task.task_id, final_status, outcome=outcome.__dict__,
        )
        _emit(
            "workflow-step-done-d" if outcome.succeeded else "workflow-step-blocked-d",
            trace_id=workflow_id,
            parent_id=start_event,
            payload={
                "title": step_task.title,
                "succeeded": outcome.succeeded,
                "summary": outcome.summary[:300],
                "artifacts": outcome.artifacts[:20],
                "error": outcome.error[:300],
            },
        )
        return outcome

    # ─── 4. Check — workflow status overview ─────────────────────────────

    def check(self, workflow_id: str) -> dict[str, Any]:
        """Snapshot the workflow's progress. Returns counts + the next step."""
        steps = self.plan_steps(workflow_id)
        by_status: dict[str, int] = {}
        for s in steps:
            by_status[s.status] = by_status.get(s.status, 0) + 1
        return {
            "workflow_id": workflow_id,
            "total_steps": len(steps),
            "by_status": by_status,
            "next_step": (next_planned := self.next_planned_step(workflow_id)),
            "next_step_id": next_planned.task_id if next_planned else None,
            "complete": (
                by_status.get("done", 0) == len(steps) and len(steps) > 0
            ),
        }

    # ─── 5. Summarize — close the workflow ───────────────────────────────

    def summarize(
        self,
        workflow_id: str,
        summary: str,
        succeeded: Optional[bool] = None,
    ) -> None:
        """Mark the workflow root done with a summary outcome."""
        check = self.check(workflow_id)
        if succeeded is None:
            succeeded = check["complete"]
        outcome = {
            "summary": summary,
            "succeeded": succeeded,
            "step_breakdown": check["by_status"],
            "total_steps": check["total_steps"],
        }
        final_status = "done" if succeeded else "blocked"
        self._projects.set_task_status(workflow_id, final_status, outcome=outcome)

    # ─── Drive the loop in one call (synchronous, for scripts) ──────────

    def run_to_completion(
        self,
        workflow_id: str,
        max_steps: int = 100,
    ) -> dict[str, Any]:
        """Step until the workflow has no more planned steps or max_steps
        is reached. Returns the final check() snapshot.

        For long-running or async workflows you'll call step() externally
        from your loop; this helper is for short, synchronous tasks
        (e.g., the smoke test, simple operator-triggered jobs).
        """
        for _ in range(max_steps):
            outcome = self.step(workflow_id)
            if outcome is None:
                break
            if not outcome.succeeded:
                # Blocked; the loop stops and waits for operator review.
                break
        return self.check(workflow_id)


__all__ = [
    "AgenticLoop",
    "PlanStep", "StepOutcome",
    "ToolHandler", "default_noop_handler",
]
