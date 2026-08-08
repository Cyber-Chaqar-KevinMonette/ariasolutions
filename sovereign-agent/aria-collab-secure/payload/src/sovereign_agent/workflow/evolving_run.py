"""
╔══════════════════════════════════════════════════════════════════════════╗
║  evolving_run.py — the self-aware, gap-closing run orchestrator            ║
║                                                                            ║
║  Composes the pieces Aria already has into one flow:                       ║
║    maturity gate → plan → gap analysis → variant routing → gated execute   ║
║                                                                            ║
║  What it adds over GatedAgenticRun:                                        ║
║    • Before running, it works out which subsystems the plan needs, which   ║
║      she has, and which are missing — and drafts proposals for the gaps.   ║
║    • It picks the best-fitting variant of each needed capability for the   ║
║      flow (a self-answerable choice).                                      ║
║    • It gates execution per-step through AuthorityPolicy, so consequential ║
║      and self-modifying steps stop for you while reversible ones flow.     ║
║    • If a new need surfaces mid-run, it records it into the plan and (for  ║
║      missing capabilities) drafts a proposal, rather than silently acting. ║
║                                                                            ║
║  It never writes code into the live package and never executes a           ║
║  consequential step without going through the approval gate.               ║
║                                                                            ║
║  v0.2.35.0                                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from sovereign_agent.workflow.agentic_loop import AgenticLoop, PlanStep
from sovereign_agent.workflow.capabilities import (
    AuthorityDecision, AuthorityPolicy, CapabilityRegistry, GapReport,
    RankedVariant, VariantRouter, analyze_gaps, looks_self_modifying, _emit,
    _new_trace_id,
)

logger = logging.getLogger(__name__)

# An approval callback: given a step and the policy's reading of it, return
# True to run it, False to hold. None means "use the safe programmatic
# default" (reversible runs, consequential holds).
ApproveFn = Callable[[PlanStep, AuthorityDecision], bool]


def _task_to_step(task: Any) -> PlanStep:
    """Rebuild a PlanStep from a stored task's JSON description."""
    try:
        spec = json.loads(task.description or "{}")
    except Exception:  # noqa: BLE001
        spec = {}
    return PlanStep(
        title=task.title,
        description=spec.get("description", ""),
        action_kind=spec.get("action_kind", "note"),
        action_input=spec.get("action_input", {}) or {},
        estimated_seconds=int(spec.get("estimated_seconds", 0) or 0),
    )


@dataclass
class EvolvingPlan:
    goal: str
    flow: str
    band: str
    clarifying_questions: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    gap_report: Optional[GapReport] = None
    # action_kind -> ranked variants (best first)
    variant_choices: dict[str, list[RankedVariant]] = field(default_factory=dict)
    proposals_written: list[str] = field(default_factory=list)

    def best_variant(self, action_kind: str) -> Optional[RankedVariant]:
        ranked = self.variant_choices.get(action_kind) or []
        return ranked[0] if ranked else None


@dataclass
class EvolvingResult:
    goal: str
    decision: str               # executed | paused_for_review | needs_capability
                                # | needs_clarification | blocked
    plan: EvolvingPlan
    workflow_id: Optional[str] = None
    final_status: Optional[dict[str, Any]] = None
    notes: list[str] = field(default_factory=list)


class EvolvingAgenticRun:
    """The flagship orchestrator behind ``sov agentic``."""

    def __init__(
        self,
        loop: AgenticLoop,
        *,
        planner: Any = None,
        scorer: Any = None,
        registry: Optional[CapabilityRegistry] = None,
        policy: Optional[AuthorityPolicy] = None,
        router: Optional[VariantRouter] = None,
        proposals_root: Optional[Path] = None,
        self_roots: Optional[list[Path]] = None,
        request_store: Any = None,
    ):
        self._loop = loop
        self._requests = request_store
        if planner is None:
            from sovereign_agent.workflow.handlers.natural_language import (
                LLMNaturalLanguagePlanner,
            )
            planner = LLMNaturalLanguagePlanner()
        if scorer is None:
            from sovereign_agent.intent.maturity import IntentMaturityScorer
            scorer = IntentMaturityScorer()
        self._planner = planner
        self._scorer = scorer
        self._registry = registry or CapabilityRegistry.from_loop(loop)
        self._policy = policy or AuthorityPolicy()
        self._router = router or VariantRouter()
        self._proposals_root = proposals_root or Path.cwd() / "proposals" / "capabilities"
        self._self_roots = self_roots or []

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def _file_request(self, kind: str, title: str, *, body: str = "",
                      workflow_id: str = "") -> Optional[str]:
        """File a collaboration request if an inbox is wired. Returns the id."""
        if self._requests is None:
            return None
        try:
            req = self._requests.open(kind, title, body=body, workflow_id=workflow_id)
            return req.request_id
        except Exception as exc:  # noqa: BLE001
            logger.debug("could not file request: %r", exc)
            return None

    # ── Planning (no side effects, no execution) ─────────────────────────

    def plan_only(self, goal: str, *, flow: str = "") -> EvolvingPlan:
        """Score, plan, analyze gaps, route variants, and draft proposals for
        anything missing. Writes proposal *drafts* to disk (safe) but does not
        touch the package or execute anything."""
        assessment = self._scorer.assess(goal, context_hint=flow or None)
        band = assessment.band
        trace = _new_trace_id()

        if band == "M0":
            _emit("workflow-clarify-d", trace_id=trace,
                  payload={"goal": goal, "band": band,
                           "questions": assessment.suggested_clarifications})
            return EvolvingPlan(goal=goal, flow=flow, band=band,
                                clarifying_questions=assessment.suggested_clarifications)

        steps = self._planner.plan(goal)
        gap = analyze_gaps(steps, self._registry, goal=goal)

        # Variant routing for each needed kind (self-answerable choice).
        variant_choices: dict[str, list[RankedVariant]] = {}
        for kind in gap.needed:
            ranked = self._router.rank(f"{kind}.default", flow, self._registry)
            if ranked:
                variant_choices[kind] = ranked

        _emit("workflow-plan-d", trace_id=trace,
              payload={"goal": goal, "band": band, "flow": flow,
                       "steps": [s.title for s in steps],
                       "needs": gap.needed, "missing": gap.missing})

        proposals_written: list[str] = []
        if gap.has_gaps:
            _emit("workflow-gap-d", trace_id=trace,
                  payload={"missing": gap.missing,
                           "proposals": [p.filename for p in gap.proposals]})
            for spec in gap.proposals:
                try:
                    path = spec.write_proposal(self._proposals_root)
                    proposals_written.append(str(path))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("proposal write failed for %s: %r",
                                 spec.action_kind, exc)

        return EvolvingPlan(
            goal=goal, flow=flow, band=band, steps=steps, gap_report=gap,
            variant_choices=variant_choices, proposals_written=proposals_written,
        )

    # ── Execution (gated, per-step) ──────────────────────────────────────

    def execute(
        self,
        goal: str,
        project_id: str,
        *,
        flow: str = "",
        approve: Optional[ApproveFn] = None,
        allow_missing: bool = False,
        max_steps: int = 100,
    ) -> EvolvingResult:
        plan = self.plan_only(goal, flow=flow)

        if plan.band == "M0":
            rid = self._file_request(
                "question", f"Need clarification: {goal[:60]}",
                body="\n".join(f"• {q}" for q in plan.clarifying_questions))
            notes = [f"❓ filed request {rid[-6:]}"] if rid else []
            return EvolvingResult(goal=goal, decision="needs_clarification",
                                  plan=plan, notes=notes)

        if plan.gap_report and plan.gap_report.has_gaps and not allow_missing:
            rid = self._file_request(
                "blocker", f"Missing subsystem(s): {', '.join(plan.gap_report.missing)}",
                body=("To pursue: " + goal + "\n\nDrafted proposals:\n" +
                      "\n".join(f"• {p}" for p in plan.proposals_written)))
            note = (f"missing subsystems: {', '.join(plan.gap_report.missing)}. "
                    f"Drafted {len(plan.proposals_written)} proposal(s) for review.")
            if rid:
                note += f"  🚧 filed request {rid[-6:]}"
            return EvolvingResult(goal=goal, decision="needs_capability", plan=plan,
                                  notes=[note])

        # M1 → write the plan, don't execute (simulate for review).
        workflow_id = self._loop.intake(project_id, goal)
        self._loop.write_plan(workflow_id, plan.steps)

        if plan.band == "M1":
            self._loop.summarize(
                workflow_id,
                summary=f"M1 (vague-but-benign) — plan written, not executed.",
                succeeded=False)
            _emit("workflow-simulated-d", trace_id=workflow_id,
                  payload={"band": plan.band, "plan": [s.title for s in plan.steps]})
            rid = self._file_request(
                "decision", f"Plan ready for review: {goal[:60]}",
                body="Steps:\n" + "\n".join(f"{i}. {s.title}"
                                            for i, s in enumerate(plan.steps, 1)),
                workflow_id=workflow_id)
            notes = ["M1: plan written for your review, not executed."]
            if rid:
                notes.append(f"🧭 filed request {rid[-6:]}")
            return EvolvingResult(goal=goal, decision="paused_for_review", plan=plan,
                                  workflow_id=workflow_id, notes=notes)

        # M2/M3 → gated step loop.
        notes: list[str] = []
        for _ in range(max_steps):
            nxt = self._loop.next_planned_step(workflow_id)
            if nxt is None:
                break
            step = _task_to_step(nxt)
            modifies_self = looks_self_modifying(step, self_roots=self._self_roots)
            decision = self._policy.assess(step.action_kind, modifies_self=modifies_self)

            if decision.requires_human:
                approved = approve(step, decision) if approve else False
                if not approved:
                    _emit("workflow-step-held-d", trace_id=workflow_id,
                          payload={"title": step.title, "kind": step.action_kind,
                                   "reason": decision.reason})
                    notes.append(f"held for review: {step.title} ({decision.reason})")
                    kind = "approval"
                    rid = self._file_request(
                        kind, f"Approve step: {step.title}",
                        body=(f"kind: {step.action_kind}\ninput: {step.action_input}\n"
                              f"why it's held: {decision.reason}"),
                        workflow_id=workflow_id)
                    if rid:
                        notes.append(f"🛂 filed request {rid[-6:]}")
                    self._loop.summarize(
                        workflow_id,
                        summary=f"paused: step '{step.title}' awaiting your approval",
                        succeeded=False)
                    return EvolvingResult(goal=goal, decision="paused_for_review",
                                          plan=plan, workflow_id=workflow_id,
                                          notes=notes,
                                          final_status=self._loop.check(workflow_id))

            outcome = self._loop.step(workflow_id)
            if outcome is None:
                break

            # Mid-run discovery: a handler can flag a freshly-needed capability.
            discovered = (outcome.extra or {}).get("needs_capability")
            if discovered:
                self._handle_discovery(workflow_id, discovered, goal, notes)

            if not outcome.succeeded:
                notes.append(f"blocked at '{step.title}': {outcome.error or outcome.summary}")
                break

        final = self._loop.check(workflow_id)
        self._loop.summarize(
            workflow_id,
            summary=f"M{plan.band[1]} agentic run finished (complete={final['complete']})",
            succeeded=final["complete"])
        _emit("workflow-complete-d", trace_id=workflow_id,
              payload={"band": plan.band, "succeeded": final["complete"],
                       "by_status": final.get("by_status")})

        decision = "executed" if final["complete"] else "blocked"
        return EvolvingResult(goal=goal, decision=decision, plan=plan,
                              workflow_id=workflow_id, final_status=final, notes=notes)

    def _handle_discovery(self, workflow_id: str, kind: str, goal: str,
                          notes: list[str]) -> None:
        """A capability need surfaced mid-run. Record it into the plan; draft a
        proposal if it's missing. We deliberately do NOT auto-append a
        side-effecting step — discovered consequential work goes back through
        a fresh plan/approval, not a silent insertion."""
        _emit("workflow-gap-d", trace_id=workflow_id,
              payload={"discovered_midrun": kind})
        gap = analyze_gaps([PlanStep(title=f"need:{kind}", description="discovered",
                                     action_kind=kind, action_input={})],
                           self._registry, goal=goal)
        if gap.has_gaps:
            for spec in gap.proposals:
                try:
                    path = spec.write_proposal(self._proposals_root)
                    notes.append(f"discovered missing subsystem {kind!r}; drafted {path.name}")
                except Exception:  # noqa: BLE001
                    pass
        # Append a visible note step so the discovery is on the record.
        try:
            self._loop.append_step(workflow_id, PlanStep(
                title=f"(discovered) need for {kind}",
                description=f"Surfaced mid-run while pursuing: {goal}",
                action_kind="note",
                action_input={"text": f"capability {kind} needed", "discovered": True}))
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "EvolvingAgenticRun", "EvolvingPlan", "EvolvingResult", "ApproveFn",
    "_task_to_step",
]
