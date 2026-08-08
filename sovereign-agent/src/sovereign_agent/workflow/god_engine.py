"""
workflow/god_engine.py — GodTierEngine (M30)

Wraps AgenticLoop with:
  - step_with_recovery(): retry chain with alternatives; escalates to blocker after max_attempts
  - verify_step(): falsifiability gate — evaluate a success criterion against step artifacts
  - validate_deps(): check produces/consumes DAG before execution begins

These capabilities are exposed as agent tools in god_workflow_tools.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .safe_eval import safe_eval  # workflow-safe-eval-import-d


@dataclass
class GodStepOutcome:
    """Outcome from step_with_recovery — richer than StepOutcome."""
    workflow_id: str
    step_id: str
    succeeded: bool
    summary: str
    attempts: int = 1
    alternative_used: bool = False
    error: str = ""
    artifacts: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyOutcome:
    """Outcome from verify_step falsifiability gate."""
    step_id: str
    criteria: str
    verdict: str   # "verified" | "unverified" | "skipped"
    reasoning: str = ""


@dataclass
class DepsReport:
    """Result from validate_deps DAG check."""
    workflow_id: str
    broken: list[dict[str, str]] = field(default_factory=list)
    ok: bool = True
    summary: str = ""


class GodTierEngine:
    """Wraps AgenticLoop with retry chains, alternatives, falsifiability gates,
    and dependency validation. Uses the same persistence layer as the base loop."""

    def __init__(self, loop: Any, projects: Any) -> None:
        self._loop = loop
        self._projects = projects

    # ── 1. step_with_recovery ────────────────────────────────────────────────

    def step_with_recovery(
        self,
        workflow_id: str,
        max_attempts: int = 3,
    ) -> GodStepOutcome | None:
        """Execute the next planned step. On failure, try declared alternatives.
        After max_attempts, mark step blocked with a full attempt log."""
        from sovereign_agent.workflow.agentic_loop import StepOutcome

        step_task = self._loop.next_planned_step(workflow_id)
        if step_task is None:
            return None

        step_id = step_task.task_id
        desc = {}
        try:
            desc = json.loads(step_task.description or "{}")
        except (json.JSONDecodeError, TypeError):
            pass

        action_input = desc.get("action_input", {})
        alternatives = action_input.get("alternatives", [])
        attempt_log: list[dict[str, Any]] = []

        # Try primary
        outcome = self._loop.step(workflow_id)
        attempt_log.append({"attempt": 1, "succeeded": outcome.succeeded if outcome else False,
                             "error": outcome.error if outcome else "no outcome"})

        if outcome and outcome.succeeded:
            return GodStepOutcome(
                workflow_id=workflow_id,
                step_id=step_id,
                succeeded=True,
                summary=outcome.summary,
                attempts=1,
                artifacts=outcome.artifacts,
                extra=outcome.extra,
            )

        # Try alternatives
        for i, alt in enumerate(alternatives[:max_attempts - 1], start=2):
            alt_input = alt.get("action_input", {})
            alt_kind = alt.get("action_kind", desc.get("action_kind", "note"))
            # Mutate the step in place for retry
            updated_desc = {**desc, "action_kind": alt_kind, "action_input": alt_input}
            try:
                self._projects.update_task_description(
                    step_id, json.dumps(updated_desc)
                )
                self._projects.set_task_status(step_id, "planned")
            except Exception:  # noqa: BLE001
                pass
            outcome = self._loop.step(workflow_id)
            attempt_log.append({
                "attempt": i,
                "alternative": alt,
                "succeeded": outcome.succeeded if outcome else False,
                "error": outcome.error if outcome else "no outcome",
            })
            if outcome and outcome.succeeded:
                return GodStepOutcome(
                    workflow_id=workflow_id,
                    step_id=step_id,
                    succeeded=True,
                    summary=f"[alt {i}] {outcome.summary}",
                    attempts=i,
                    alternative_used=True,
                    artifacts=outcome.artifacts,
                    extra=outcome.extra,
                )

        # All attempts failed — escalate
        last_error = (outcome.error if outcome else "all alternatives exhausted")
        return GodStepOutcome(
            workflow_id=workflow_id,
            step_id=step_id,
            succeeded=False,
            summary=f"blocked after {len(attempt_log)} attempts",
            attempts=len(attempt_log),
            error=last_error,
            extra={"attempt_log": attempt_log},
        )

    # ── 2. verify_step ───────────────────────────────────────────────────────

    def verify_step(
        self,
        workflow_id: str,
        step_id: str,
        criteria: str,
    ) -> VerifyOutcome:
        """Falsifiability gate: evaluate criteria against step state.

        criteria can reference:
          - exit_code: int  (for shell steps)
          - artifacts: list[str]
          - succeeded: bool

        Example: "exit_code == 0"  or  "len(artifacts) > 0"
        """
        step_task = self._projects.get_task(step_id)
        if step_task is None:
            return VerifyOutcome(
                step_id=step_id,
                criteria=criteria,
                verdict="skipped",
                reasoning=f"step {step_id!r} not found",
            )

        # Build evaluation namespace from step metadata
        ns: dict[str, Any] = {
            "succeeded": step_task.status == "done",
            "status": step_task.status,
            "exit_code": 0,
            "artifacts": [],
        }
        try:
            meta = json.loads(step_task.description or "{}")
            extra = meta.get("extra", {})
            ns["exit_code"] = extra.get("exit_code", 0)
            ns["artifacts"] = meta.get("artifacts", [])
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            result = safe_eval(criteria, ns)
            verdict = "verified" if bool(result) else "unverified"
            reasoning = f"eval({criteria!r}) → {result!r}"
        except Exception as exc:  # noqa: BLE001
            verdict = "unverified"
            reasoning = f"eval error: {exc}"

        return VerifyOutcome(
            step_id=step_id,
            criteria=criteria,
            verdict=verdict,
            reasoning=reasoning,
        )

    # ── 3. validate_deps ─────────────────────────────────────────────────────

    def validate_deps(self, workflow_id: str) -> DepsReport:
        """Check that every step's consumes items were produced by prior steps.

        Steps can declare in their action_input:
          "produces": ["test_results", "build_artifact"]
          "consumes": ["source_files"]

        validate_deps checks the DAG is consistent before execution begins.
        """
        steps = self._loop.plan_steps(workflow_id)
        produced: set[str] = set()
        broken: list[dict[str, str]] = []

        for step in steps:
            try:
                desc = json.loads(step.description or "{}")
                action_input = desc.get("action_input", {})
                consumes = action_input.get("consumes", [])
                produces = action_input.get("produces", [])
            except (json.JSONDecodeError, TypeError):
                consumes, produces = [], []

            for item in consumes:
                if item not in produced:
                    broken.append({
                        "step": step.task_id,
                        "step_title": step.title,
                        "missing": item,
                        "produced_so_far": sorted(produced),
                    })
            produced.update(produces)

        ok = len(broken) == 0
        summary = (
            "DAG is valid — all dependencies satisfied."
            if ok
            else f"DAG has {len(broken)} broken dependency/dependencies."
        )
        return DepsReport(workflow_id=workflow_id, broken=broken, ok=ok, summary=summary)
