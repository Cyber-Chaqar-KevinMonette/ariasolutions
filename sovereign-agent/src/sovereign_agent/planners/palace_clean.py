"""palace-clean planner: deterministic proposal generation for cleanup
candidates, based on heuristics. No model needed.

Differs from palace-reflect: reflect uses the orchestrator to interpret
the understanding and surface insights. clean uses fixed rules to
mechanically propose cleanup actions for clear-cut cases.

Both produce proposals in the same store. Both require operator approval
before any change applies. The split exists because some cleanup is
obvious enough not to need a model (orphan removal, low-confidence
triple invalidation), while reorganization needs judgment.

What it proposes:
  1. Remove orphan triples (broken refs).
  2. Invalidate low-confidence triples (< 0.3).
  3. Invalidate self-referential triples.
  4. Invalidate stoplist-object triples.
  5. Merge duplicate entity groups (canonical = first by id, others merge in).

Each proposal includes the rationale. Operator approves selectively.
"""
from __future__ import annotations

from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class PalaceCleanPlanner(Planner):
    name = "palace-clean"
    description = "Deterministic cleanup proposal generation. Pure-Python, no model."

    def required_args(self) -> tuple[str, ...]:
        return ()

    def plan(self, **kwargs: Any) -> PlanResult:
        from ..palace import open_palace
        from ..palace_scan import scan_palace

        palace = open_palace()
        try:
            understanding = scan_palace(palace)
        finally:
            palace.close()

        if understanding.is_empty():
            raise PlannerError(
                "palace-clean: palace is empty. Run palace-mine first."
            )

        # Each step generates ONE proposal. Steps are deterministic so the
        # plan is reproducible.
        steps: list[Step] = []
        idx = 0

        # Orphan triples → propose removal
        for triple_id in understanding.orphans.orphan_triples:
            steps.append(Step(
                id=idx, kind="palace_clean_propose",
                args={
                    "kind": "clean",
                    "title": f"Remove orphan triple {triple_id}",
                    "rationale": "Triple references entities that don't exist in the palace.",
                    "action": {"type": "remove_triple", "triple_id": triple_id},
                    "source": "palace-clean planner",
                },
                required_model="none",
            ))
            idx += 1

        # Low-confidence triples → propose invalidation
        for triple_id in understanding.suspicion.low_confidence:
            steps.append(Step(
                id=idx, kind="palace_clean_propose",
                args={
                    "kind": "clean",
                    "title": f"Invalidate low-confidence triple {triple_id}",
                    "rationale": "Confidence < 0.4. Likely noise from regex extraction.",
                    "action": {"type": "remove_triple", "triple_id": triple_id},
                    "source": "palace-clean planner",
                },
                required_model="none",
            ))
            idx += 1

        # Self-referential triples
        for triple_id in understanding.suspicion.self_referential:
            steps.append(Step(
                id=idx, kind="palace_clean_propose",
                args={
                    "kind": "clean",
                    "title": f"Invalidate self-referential triple {triple_id}",
                    "rationale": "Subject == object. Almost certainly an extraction artifact.",
                    "action": {"type": "remove_triple", "triple_id": triple_id},
                    "source": "palace-clean planner",
                },
                required_model="none",
            ))
            idx += 1

        # Stoplist-object triples
        for triple_id in understanding.suspicion.stoplist_objects:
            steps.append(Step(
                id=idx, kind="palace_clean_propose",
                args={
                    "kind": "clean",
                    "title": f"Invalidate stoplist-object triple {triple_id}",
                    "rationale": "Object is a stopword (the/a/this/etc). Not a real fact.",
                    "action": {"type": "remove_triple", "triple_id": triple_id},
                    "source": "palace-clean planner",
                },
                required_model="none",
            ))
            idx += 1

        # Duplicate entity merges
        for group in understanding.duplicates.duplicate_entity_groups:
            if len(group) < 2:
                continue
            canonical = group[0]
            duplicates = group[1:]
            steps.append(Step(
                id=idx, kind="palace_clean_propose",
                args={
                    "kind": "reorganize",
                    "title": f"Merge {len(duplicates)} duplicate entities into {canonical}",
                    "rationale": (
                        f"These entities have the same normalized name; "
                        f"likely the same thing under different display forms."
                    ),
                    "action": {
                        "type": "merge_entities",
                        "canonical_id": canonical,
                        "duplicate_ids": duplicates,
                    },
                    "source": "palace-clean planner",
                },
                required_model="none",
            ))
            idx += 1

        if not steps:
            raise PlannerError(
                "palace-clean: nothing to clean. The palace looks tidy."
            )

        return PlanResult(
            goal=f"Generate {len(steps)} cleanup proposals (operator review required)",
            steps=steps,
            output_path=None,
            notes="proposals land in proposals/, all status='pending'",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        return f"Generate {step.args.get('kind', '?')} proposal: {step.args.get('title', '?')}"


def execute_palace_clean_step(step: Step) -> str:
    """Pure-Python executor: write a proposal into the proposal store."""
    from ..proposals import open_store

    args = step.args
    store = open_store()
    p = store.create(
        kind=args["kind"],
        title=args["title"],
        action=args["action"],
        rationale=args.get("rationale", ""),
        source=args.get("source", ""),
    )
    return f"created proposal {p.id} ({p.kind}): {p.title[:80]}"
