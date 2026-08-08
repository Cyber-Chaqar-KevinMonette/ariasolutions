"""
tools/workflow_tools.py — Persistent workflow tools (M28, aria-workflow-wire)

Three tools that expose the AgenticLoop skeleton to the agent:

  workflow_create (T1): Decompose a goal into plan steps; returns workflow_id.
  workflow_step   (T1): Execute the next pending step; returns outcome.
  workflow_status (T0): Query progress without executing anything.

Workflows persist in atoms.db via ProjectsManager. They survive cockpit
restarts — call workflow_status(workflow_id) to find where a workflow left
off, then workflow_step(workflow_id) to resume.

Handlers wired here: note (noop), shell, file_write, file_read — all scoped
to SETTINGS.paths.sandbox_dir. The shell handler uses its default allowlist.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from sovereign_agent.config import SETTINGS
from .base import Tool, ToolResult


# ── Handler factory ───────────────────────────────────────────────────────


def _open_loop():
    """Open atoms.db → ProjectsManager → AgenticLoop with standard handlers.

    Returns (loop, projects). Handlers registered: note (built-in), shell,
    file_write, file_read — all scoped to the sandbox directory.
    """
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.persistence.projects import ProjectsManager
    from sovereign_agent.workflow.agentic_loop import AgenticLoop
    from sovereign_agent.workflow.handlers import (
        ShellHandler, FileWriteHandler, FileReadHandler,
    )

    store = ErebloStore(SETTINGS.paths.atoms_db)
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)

    sandbox = SETTINGS.paths.sandbox_dir
    sandbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    loop.register_tool_handler("shell", ShellHandler())
    loop.register_tool_handler("file_write", FileWriteHandler([sandbox]))
    loop.register_tool_handler("file_read", FileReadHandler([sandbox]))

    return loop, projects


# ── Shared step-input schema ──────────────────────────────────────────────


_ALLOWED_ACTION_KINDS = frozenset({"note", "shell", "file_write", "file_read"})


class _PlanStepInput(BaseModel):
    title: str = Field(description="Short step title (≤80 chars)")
    action_kind: str = Field(
        description="note | shell | file_write | file_read"
    )
    action_input: dict = Field(
        default_factory=dict,
        description=(
            "Payload for the handler. "
            "shell: {argv: [str, ...]}, "
            "file_write: {path: str, content: str}, "
            "file_read: {path: str}, "
            "note: {text: str}"
        ),
    )
    description: str = Field(default="", description="Optional longer step description")
    estimated_seconds: int = Field(default=0, ge=0)


# ── workflow_create (T1) ──────────────────────────────────────────────────


class _CreateArgs(BaseModel):
    goal: str = Field(description="The overall goal the workflow should accomplish")
    project_name: str = Field(
        default="workflow",
        description="Project to file the workflow under (created if absent)",
    )
    steps: list[_PlanStepInput] = Field(
        min_length=1,
        description="Ordered list of plan steps",
    )


class WorkflowCreateTool(Tool[_CreateArgs]):
    name = "workflow_create"
    tier = 1
    description = (
        "Create a persistent, multi-step workflow. Returns a workflow_id — "
        "call workflow_step(workflow_id) to execute one step at a time. "
        "Workflows survive cockpit restarts; use workflow_status to resume. "
        "action_kinds: note (no side-effect), shell (allowlisted command), "
        "file_write (writes inside sandbox), file_read (reads inside sandbox). "
        "FAILURE MODES: invalid_action_kind, db_locked, project_error."
    )
    failure_modes = ("invalid_action_kind", "db_locked", "project_error")
    Args = _CreateArgs

    async def execute(self, args: _CreateArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            for step in args.steps:
                if step.action_kind not in _ALLOWED_ACTION_KINDS:
                    return ToolResult(
                        ok=False,
                        error=(
                            f"unknown action_kind {step.action_kind!r} in step "
                            f"'{step.title}'; allowed: {sorted(_ALLOWED_ACTION_KINDS)}"
                        ),
                    )

            loop, projects = _open_loop()

            proj = projects.get_project_by_name(args.project_name)
            if proj is None:
                project_id = projects.create_project(
                    args.project_name,
                    description="Created by workflow_create tool",
                )
            else:
                project_id = proj.project_id

            from sovereign_agent.workflow.agentic_loop import PlanStep

            plan_steps = [
                PlanStep(
                    title=step.title[:80],
                    description=step.description or step.title,
                    action_kind=step.action_kind,
                    action_input=step.action_input,
                    estimated_seconds=step.estimated_seconds,
                )
                for step in args.steps
            ]

            workflow_id = loop.intake(project_id, args.goal)
            step_ids = loop.write_plan(workflow_id, plan_steps)

            return ToolResult(
                ok=True,
                output={
                    "workflow_id": workflow_id,
                    "project_id": project_id,
                    "project_name": args.project_name,
                    "step_count": len(step_ids),
                    "message": (
                        f"Workflow created with {len(step_ids)} step(s). "
                        "Call workflow_step(workflow_id) to begin execution. "
                        "Call workflow_status(workflow_id) to monitor progress."
                    ),
                },
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


# ── workflow_step (T1) ────────────────────────────────────────────────────


class _StepArgs(BaseModel):
    workflow_id: str = Field(description="The workflow_id returned by workflow_create")


class WorkflowStepTool(Tool[_StepArgs]):
    name = "workflow_step"
    tier = 1
    description = (
        "Execute the next planned step in a workflow. Call repeatedly until "
        "workflow_status shows no 'planned' steps remain. "
        "Returns succeeded, summary, artifacts, and any error. "
        "If a step fails (succeeded=False), the step is marked 'blocked' and "
        "the workflow waits for operator review before continuing. "
        "FAILURE MODES: no_planned_steps, handler_not_registered, db_locked."
    )
    failure_modes = ("no_planned_steps", "handler_not_registered", "db_locked")
    Args = _StepArgs

    async def execute(self, args: _StepArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            loop, projects = _open_loop()

            root = projects.get_task(args.workflow_id)
            if root is None:
                return ToolResult(
                    ok=False,
                    error=f"workflow_id {args.workflow_id!r} not found",
                )

            outcome = loop.step(args.workflow_id)

            if outcome is None:
                return ToolResult(
                    ok=True,
                    output={
                        "no_planned_steps": True,
                        "message": (
                            "No planned steps remain. "
                            "Call workflow_status(workflow_id) to see the final state."
                        ),
                    },
                )

            return ToolResult(
                ok=True,
                output={
                    "succeeded": outcome.succeeded,
                    "summary": outcome.summary,
                    "error": outcome.error or None,
                    "artifacts": outcome.artifacts,
                    "started_at": outcome.started_at,
                    "completed_at": outcome.completed_at,
                    "extra": {
                        k: v for k, v in outcome.extra.items()
                        if k not in ("stdout", "stderr")
                    },
                    "stdout": outcome.extra.get("stdout", ""),
                    "stderr": outcome.extra.get("stderr", ""),
                },
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


# ── workflow_status (T0) ──────────────────────────────────────────────────


class _StatusArgs(BaseModel):
    workflow_id: str = Field(description="The workflow_id to query")


class WorkflowStatusTool(Tool[_StatusArgs]):
    name = "workflow_status"
    tier = 0
    description = (
        "Query workflow progress without executing anything. "
        "Returns total step count, counts by status (planned/in_progress/done/blocked), "
        "whether the workflow is complete, and the title of the next step. "
        "Use this after restart to find where a workflow left off before resuming. "
        "FAILURE MODES: workflow_not_found, db_locked."
    )
    failure_modes = ("workflow_not_found", "db_locked")
    Args = _StatusArgs

    async def execute(self, args: _StatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            loop, projects = _open_loop()

            root = projects.get_task(args.workflow_id)
            if root is None:
                return ToolResult(
                    ok=False,
                    error=f"workflow_id {args.workflow_id!r} not found",
                )

            status = loop.check(args.workflow_id)
            steps = loop.plan_steps(args.workflow_id)

            step_list = [
                {
                    "ordinal": s.ordinal,
                    "title": s.title,
                    "status": s.status,
                }
                for s in steps
            ]

            next_step = status.get("next_step")
            return ToolResult(
                ok=True,
                output={
                    "workflow_id": args.workflow_id,
                    "goal": root.title.removeprefix("workflow: "),
                    "total_steps": status["total_steps"],
                    "by_status": status["by_status"],
                    "complete": status["complete"],
                    "next_step_title": next_step.title if next_step else None,
                    "next_step_kind": (
                        __import__("json", fromlist=[]).loads(next_step.description).get("action_kind")
                        if next_step else None
                    ),
                    "steps": step_list,
                },
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


__all__ = ["WorkflowCreateTool", "WorkflowStepTool", "WorkflowStatusTool"]
