"""impact-score planner: ask the orchestrator to score an Impact Vector
for a given action description. Emits a Knowledge Atom storing the IV.

One step per planning invocation. The model is asked to:
  1. Read the action description and any provided context.
  2. Score 12 cells (3 dimensions × 4 scales).
  3. Mark each with a confidence (0-1).
  4. Provide brief notes per cell (why this score).
  5. Emit the result via the impact_score tool, which writes the atom.

Tagged 'orchestrator'. The model is the right caller because IV scoring
is judgment-heavy — not pure pattern matching.

Output: the atom_id of the newly created Impact Vector atom. Operator
reviews via `sov impact show <atom-id>`. The IV is then queryable
through `memory_search` (atoms.db) like any other atom.

The IV is FLAGGED, never autonomously enforced. If the IV trips a
threshold (Symbiosis canary, 7th-gen escalation, Tier ≥ 3), the operator
is notified — the action does not auto-refuse.
"""
from __future__ import annotations

from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class ImpactScorePlanner(Planner):
    name = "impact-score"
    description = (
        "Score the multi-scale impact of an action via the orchestrator. "
        "Emits a 3×4 Impact Vector as a Knowledge Atom with confidence "
        "per cell. Operator reviews; system never auto-rejects."
    )

    def required_args(self) -> tuple[str, ...]:
        return ("action_label",)

    def plan(self, **kwargs: Any) -> PlanResult:
        action_label = kwargs.get("action_label")
        action_description = kwargs.get("action_description") or action_label
        context = kwargs.get("context") or ""

        if not action_label:
            raise PlannerError(
                "impact-score: 'action_label' is required (one-line action summary)"
            )

        step = Step(
            id=0,
            kind="impact_score_action",
            args={
                "action_label": str(action_label),
                "action_description": str(action_description),
                "context": str(context),
            },
            required_model="orchestrator",
        )
        return PlanResult(
            goal=f"Score Impact Vector for: {action_label}",
            steps=[step],
            output_path=None,
            notes="emits one IV atom; operator reviews via 'sov impact show'",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        from ..impact import ADAPTIVE_FRAMING, DIMENSIONS, SCALES, PEIG_LENS

        action_label = step.args.get("action_label", "(missing)")
        action_description = step.args.get("action_description", action_label)
        context = step.args.get("context", "")

        cells_listing = []
        for dim in DIMENSIONS:
            cells_listing.append(f"  {dim} (PEIG lens: {PEIG_LENS[dim]})")
            for scale in SCALES:
                cells_listing.append(f"    - {dim[0].upper()}_{scale}")

        return f"""You are scoring an Impact Vector for an action. Read the framing carefully.

FRAMING:
{ADAPTIVE_FRAMING}

ACTION TO SCORE:
  Label: {action_label}
  Description: {action_description}
{f'  Context: {context}' if context else ''}

WHAT TO DO:
Use the impact_score tool ONCE to record a 3×4 Impact Vector for this action.
The tool stores the IV as a Knowledge Atom for the operator to review.

The 12 cells are:
{chr(10).join(cells_listing)}

For each cell, provide:
  - score in [-1, +1]: negative = harm, positive = benefit, magnitude = intensity
  - confidence in [0, 1]: how sure are you?  Be honest about uncertainty.
  - notes: brief justification (why this score, what evidence)

CRITICAL GUIDELINES:
  * Be CONSERVATIVE on scores. A 0.0 with high confidence is more honest than
    a +0.5 with low confidence when you don't really know.
  * Be HONEST on confidence. If you're guessing, mark confidence ≤ 0.4.
    The operator needs to distinguish judgments from findings.
  * If a cell genuinely doesn't apply (e.g., this action has no cosmic-scale
    impact), score it 0.0 with confidence 0.5 and note "not applicable".
  * The Symbiosis Test: M_micro < -0.3 means the action made the human less
    capable. Score honestly; a tripped canary triggers operator review,
    which is the safety property — not a punishment.
  * Don't pad scores to look thorough. Empty cells (omitted) are okay if you
    have no signal.

When you've called impact_score with the cells, you are done. Do not call
any other tools. The operator will review the resulting atom."""
