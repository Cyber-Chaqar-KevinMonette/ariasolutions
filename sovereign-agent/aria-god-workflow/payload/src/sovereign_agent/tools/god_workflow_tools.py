"""
tools/god_workflow_tools.py — God-tier workflow tools (M30)

Four tools that extend the workflow system with retry, mutation,
checkpoint, and dependency inspection:

  workflow_mutate     (T1): Replace steps from ordinal N onward with a new plan.
  workflow_retry      (T1): Reset a blocked step to planned, optionally with new input.
  workflow_checkpoint (T0): Inspect a step's outcome against a success criterion.
  workflow_deps       (T0): Show the produces/consumes DAG; flag broken dependencies.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from sovereign_agent.config import SETTINGS
from .base import Tool, ToolResult


def _open_god_engine():
    """Open the GodTierEngine with standard handlers."""
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.persistence.projects import ProjectsManager
    from sovereign_agent.workflow.agentic_loop import AgenticLoop
    from sovereign_agent.workflow.god_engine import GodTierEngine
    from sovereign_agent.workflow.handlers import (
        ShellHandler, FileWriteHandler, FileReadHandler,
    )

    store = ErebloStore(SETTINGS.paths.atoms_db)
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)

    sandbox = SETTINGS.paths.sandbox_dir
    sandbox.mkdir(parents=True, exist_ok=True)
    loop.register_tool_handler("shell", ShellHandler(sandbox))
    loop.register_tool_handler("file_write", FileWriteHandler(sandbox))
    loop.register_tool_handler("file_read", FileReadHandler(sandbox))

    engine = GodTierEngine(loop=loop, projects=projects)
    return engine, loop, projects


# ── workflow_mutate ──────────────────────────────────────────────────────────


class WorkflowMutateTool(Tool):
    """Replace workflow steps from ordinal N onward with a new plan.

    Completed steps (status='done') before from_ordinal are preserved.
    Steps at or after from_ordinal are abandoned and replaced with new_steps.
    Use when mid-run discovery shows the remaining plan needs to change.
    """

    name = "workflow_mutate"
    tier = 1
    description = (
        "Replace workflow steps from ordinal N onward with a new plan. "
        "Preserves completed steps before from_ordinal; marks replaced steps abandoned. "
        "Args: workflow_id, from_ordinal (1-based), new_steps (list of step dicts). "
        "Use when the remaining plan needs to change mid-execution."
    )
    failure_modes = (
        "workflow_id not found",
        "from_ordinal out of range",
        "new_steps contain invalid action_kind",
    )

    _VALID_KINDS = frozenset({"note", "shell", "file_write", "file_read", "llm_call"})

    class Args(BaseModel):
        workflow_id: str = Field(description="The workflow to mutate.")
        from_ordinal: int = Field(ge=1, description="Replace steps from this ordinal (1-based) onward.")
        new_steps: list[dict[str, Any]] = Field(
            description="Replacement steps. Each: {title, action_kind, action_input}."
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.workflow.agentic_loop import PlanStep

        for s in args.new_steps:
            if s.get("action_kind") not in self._VALID_KINDS:
                return ToolResult(
                    ok=False,
                    error=f"invalid action_kind {s.get('action_kind')!r} in new_steps",
                )

        try:
            engine, loop, projects = _open_god_engine()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"engine open failed: {exc}")

        root = projects.get_task(args.workflow_id)
        if root is None:
            return ToolResult(ok=False, error=f"workflow not found: {args.workflow_id!r}")

        existing = loop.plan_steps(args.workflow_id)
        abandoned = 0
        for step in existing:
            if step.ordinal is not None and step.ordinal >= args.from_ordinal:
                if step.status not in ("done",):
                    try:
                        projects.set_task_status(step.task_id, "abandoned")
                        abandoned += 1
                    except Exception:  # noqa: BLE001
                        pass

        max_existing_ordinal = max(
            (s.ordinal or 0 for s in existing if (s.ordinal or 0) < args.from_ordinal),
            default=args.from_ordinal - 1,
        )
        new_step_ids: list[str] = []
        for i, spec in enumerate(args.new_steps, start=args.from_ordinal):
            plan_step = PlanStep(
                title=spec.get("title", f"step-{i}"),
                description=spec.get("description", spec.get("title", "")),
                action_kind=spec["action_kind"],
                action_input=spec.get("action_input", {}),
            )
            sid = loop.append_step(args.workflow_id, plan_step)
            new_step_ids.append(sid)

        return ToolResult(
            ok=True,
            output={
                "workflow_id": args.workflow_id,
                "abandoned": abandoned,
                "new_step_count": len(new_step_ids),
                "new_step_ids": new_step_ids,
            },
            metadata={"from_ordinal": args.from_ordinal},
        )


# ── workflow_retry ───────────────────────────────────────────────────────────


class WorkflowRetryTool(Tool):
    """Reset a blocked step to planned, optionally with modified input.

    Use when a step is blocked and you want to try a different approach
    without replacing the whole plan. The previous attempt is logged.
    """

    name = "workflow_retry"
    tier = 1
    description = (
        "Reset a blocked workflow step to planned, optionally with new action_input or action_kind. "
        "Args: workflow_id, step_id, new_input (optional dict), new_kind (optional str). "
        "Use when a step is blocked and you want to retry with a different approach."
    )
    failure_modes = (
        "step_id not found",
        "step is not in blocked status",
        "workflow_id mismatch",
    )

    class Args(BaseModel):
        workflow_id: str = Field(description="The workflow containing the step.")
        step_id: str = Field(description="The task_id of the blocked step to retry.")
        new_input: Optional[dict[str, Any]] = Field(
            default=None, description="Replacement action_input for the retry."
        )
        new_kind: Optional[str] = Field(
            default=None, description="Replacement action_kind for the retry."
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            engine, loop, projects = _open_god_engine()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"engine open failed: {exc}")

        step = projects.get_task(args.step_id)
        if step is None:
            return ToolResult(ok=False, error=f"step not found: {args.step_id!r}")

        try:
            desc = json.loads(step.description or "{}")
        except (json.JSONDecodeError, TypeError):
            desc = {}

        if args.new_input is not None:
            desc["action_input"] = args.new_input
        if args.new_kind is not None:
            desc["action_kind"] = args.new_kind

        desc.setdefault("retry_log", [])
        desc["retry_log"].append({
            "previous_status": step.status,
            "trace_id": trace_id,
        })

        try:
            projects.update_task_description(args.step_id, json.dumps(desc))
            projects.set_task_status(args.step_id, "planned")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"retry reset failed: {exc}")

        return ToolResult(
            ok=True,
            output={
                "workflow_id": args.workflow_id,
                "step_id": args.step_id,
                "status": "planned",
                "new_kind": args.new_kind or desc.get("action_kind"),
                "message": "Step reset to planned. Call workflow_step() to execute.",
            },
        )


# ── workflow_checkpoint ──────────────────────────────────────────────────────


class WorkflowCheckpointTool(Tool):
    """Evaluate a success criterion against a completed step's outcome.

    Zero side effects — reads only. Use after critical steps to verify
    the outcome before proceeding. Returns verdict: verified|unverified|skipped.
    """

    name = "workflow_checkpoint"
    tier = 0
    description = (
        "Evaluate a success criterion against a completed step's outcome (falsifiability gate). "
        "Args: workflow_id, step_id, criteria (Python expression), description. "
        "criteria can reference: succeeded (bool), exit_code (int), artifacts (list). "
        "Returns verdict: verified | unverified | skipped."
    )
    failure_modes = (
        "step_id not found",
        "criteria evaluation error",
    )

    class Args(BaseModel):
        workflow_id: str = Field(description="The workflow containing the step.")
        step_id: str = Field(description="The step to verify.")
        criteria: str = Field(
            description="Python expression to evaluate. Variables: succeeded, exit_code, artifacts."
        )
        description: str = Field(default="", description="Human-readable checkpoint description.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            engine, loop, projects = _open_god_engine()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"engine open failed: {exc}")

        outcome = engine.verify_step(
            workflow_id=args.workflow_id,
            step_id=args.step_id,
            criteria=args.criteria,
        )

        ok = outcome.verdict == "verified"
        return ToolResult(
            ok=True,
            output={
                "step_id": args.step_id,
                "criteria": outcome.criteria,
                "verdict": outcome.verdict,
                "reasoning": outcome.reasoning,
                "description": args.description,
            },
            metadata={"verified": ok},
        )


# ── workflow_deps ────────────────────────────────────────────────────────────


class WorkflowDepsTool(Tool):
    """Show the produces/consumes dependency DAG for a workflow.

    Steps can declare in their action_input:
      "produces": ["test_results", "build_artifact"]
      "consumes": ["source_files"]

    workflow_deps checks that every consumed item was produced by a prior step.
    Call before executing to catch broken dependencies early.
    """

    name = "workflow_deps"
    tier = 0
    description = (
        "Show the produces/consumes DAG for a workflow and flag broken dependencies. "
        "Args: workflow_id. "
        "Returns: ok (bool), summary, broken list (step, missing item). "
        "Call before executing a workflow to validate the dependency graph."
    )
    failure_modes = (
        "workflow_id not found",
        "step description not parseable",
    )

    class Args(BaseModel):
        workflow_id: str = Field(description="The workflow to inspect.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            engine, loop, projects = _open_god_engine()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"engine open failed: {exc}")

        report = engine.validate_deps(args.workflow_id)

        steps = loop.plan_steps(args.workflow_id)
        dag_lines: list[str] = [f"Workflow {args.workflow_id} dependency DAG:"]
        for step in steps:
            try:
                desc = json.loads(step.description or "{}")
                ai = desc.get("action_input", {})
                produces = ai.get("produces", [])
                consumes = ai.get("consumes", [])
            except (json.JSONDecodeError, TypeError):
                produces, consumes = [], []
            parts = [f"  [{step.status}] {step.title}"]
            if consumes:
                parts.append(f"    ← consumes: {', '.join(consumes)}")
            if produces:
                parts.append(f"    → produces: {', '.join(produces)}")
            dag_lines.extend(parts)

        if report.broken:
            dag_lines.append(f"\n⚠ {len(report.broken)} broken dependency/dependencies:")
            for b in report.broken:
                dag_lines.append(f"  ✗ step '{b['step_title']}' needs '{b['missing']}'")

        return ToolResult(
            ok=True,
            output={
                "workflow_id": args.workflow_id,
                "deps_ok": report.ok,
                "summary": report.summary,
                "broken": report.broken,
                "dag": "\n".join(dag_lines),
            },
            metadata={"deps_ok": report.ok, "broken_count": len(report.broken)},
        )
