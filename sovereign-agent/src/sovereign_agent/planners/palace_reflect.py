"""palace-reflect planner: walk a palace understanding, emit one step per
section asking the orchestrator to propose reorganizations, insights, and
enhancements.

Each step writes its proposals via the orchestrator using the
``proposal_write`` tool (added in v0.2.9). No direct mutations to the
palace happen here — proposals are durable suggestions awaiting operator
approval.

Model affinity: orchestrator.

Steps emitted (one per section of the understanding that has actionable signal):
  1. reflect on rooms and distribution
  2. reflect on orphans
  3. reflect on duplicates
  4. reflect on suspicious triples
  5. reflect on top entities (potential consolidation)

If a section has nothing notable, the planner skips it. The plan is
deterministic given the same understanding input.
"""
from __future__ import annotations

from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class PalaceReflectPlanner(Planner):
    name = "palace-reflect"
    description = "Walk palace understanding, emit proposals for cleanup/insights/enhancements."

    def required_args(self) -> tuple[str, ...]:
        return ()

    def plan(self, **kwargs: Any) -> PlanResult:
        from ..palace import open_palace
        from ..palace_scan import scan_palace

        # Run the scan now so we know what to propose. Stored in step args
        # so the model sees the actual data in the goal.
        palace = open_palace()
        try:
            understanding = scan_palace(palace)
        finally:
            palace.close()

        if understanding.is_empty():
            raise PlannerError(
                "palace-reflect: palace is empty. Run palace-mine first."
            )

        steps: list[Step] = []
        section_id = 0

        # Section: distribution / room balance
        if len(understanding.rooms) > 0:
            steps.append(Step(
                id=section_id,
                kind="palace_reflect_section",
                args={
                    "section": "distribution",
                    "rooms": [
                        {"id": r.room_id, "name": r.room_name,
                         "closets": r.closet_count}
                        for r in understanding.rooms
                    ],
                    "top_entities": understanding.distribution.top_entities[:10],
                },
                required_model="orchestrator",
            ))
            section_id += 1

        # Section: orphans
        orphan_total = (
            len(understanding.orphans.orphan_closets)
            + len(understanding.orphans.orphan_entities)
            + len(understanding.orphans.orphan_triples)
        )
        if orphan_total > 0:
            steps.append(Step(
                id=section_id,
                kind="palace_reflect_section",
                args={
                    "section": "orphans",
                    "orphan_closets": understanding.orphans.orphan_closets[:20],
                    "orphan_entities": understanding.orphans.orphan_entities[:20],
                    "orphan_triples": understanding.orphans.orphan_triples[:20],
                    "totals": {
                        "closets": len(understanding.orphans.orphan_closets),
                        "entities": len(understanding.orphans.orphan_entities),
                        "triples": len(understanding.orphans.orphan_triples),
                    },
                },
                required_model="orchestrator",
            ))
            section_id += 1

        # Section: duplicates
        dup_total = (
            len(understanding.duplicates.duplicate_entity_groups)
            + len(understanding.duplicates.duplicate_closet_groups)
        )
        if dup_total > 0:
            steps.append(Step(
                id=section_id,
                kind="palace_reflect_section",
                args={
                    "section": "duplicates",
                    "entity_groups": understanding.duplicates.duplicate_entity_groups[:10],
                    "closet_groups": understanding.duplicates.duplicate_closet_groups[:10],
                },
                required_model="orchestrator",
            ))
            section_id += 1

        # Section: suspicion (low-quality triples)
        susp_total = (
            len(understanding.suspicion.low_confidence)
            + len(understanding.suspicion.self_referential)
            + len(understanding.suspicion.stoplist_objects)
        )
        if susp_total > 0:
            steps.append(Step(
                id=section_id,
                kind="palace_reflect_section",
                args={
                    "section": "suspicion",
                    "low_confidence": understanding.suspicion.low_confidence[:20],
                    "self_referential": understanding.suspicion.self_referential[:20],
                    "stoplist_objects": understanding.suspicion.stoplist_objects[:20],
                },
                required_model="orchestrator",
            ))
            section_id += 1

        if not steps:
            raise PlannerError(
                "palace-reflect: nothing notable in the understanding. "
                "Palace looks clean. (Try palace-mine on more atoms first.)"
            )

        return PlanResult(
            goal=f"Reflect on palace understanding ({len(steps)} sections)",
            steps=steps,
            output_path=None,  # proposals land in proposals/, not a single file
            notes=f"counts: {understanding.counts.closets} closets, "
                  f"{understanding.counts.entities} entities, "
                  f"{understanding.counts.triples} triples",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        section = step.args.get("section", "?")
        # Each section has its own micro-prompt. The model is asked to write
        # proposals via the proposal_write tool — never to mutate the palace
        # directly.
        common_preamble = (
            "You are reflecting on the structure of the system's memory palace. "
            "Your job is to PROPOSE changes — not to make them. "
            "Use the proposal_write tool to record each suggestion. "
            "The operator will review proposals before any are applied. "
            "Quality over quantity: 1-3 well-reasoned proposals beat 10 weak ones. "
            "Be concrete: each action must specify exactly what to change. "
            "Frame proposals adaptively: 'consider X' over 'must do X' — "
            "the operator decides what serves the work.\n\n"
        )

        if section == "distribution":
            rooms = step.args.get("rooms", [])
            top_ents = step.args.get("top_entities", [])
            return (
                common_preamble
                + f"Section: DISTRIBUTION\n"
                f"Rooms: {rooms}\n"
                f"Top mentioned entities (name, count): {top_ents}\n\n"
                "Look for: rooms with imbalanced sizes, entities mentioned across "
                "many rooms (suggesting a missing dedicated room), top entities "
                "without a related closet structure.\n"
                "Propose insights or reorganizations that would improve "
                "discoverability."
            )
        if section == "orphans":
            totals = step.args.get("totals", {})
            return (
                common_preamble
                + f"Section: ORPHANS\n"
                f"Totals: {totals}\n"
                f"Sample orphan closets (no atoms): {step.args.get('orphan_closets', [])}\n"
                f"Sample orphan entities (never referenced): {step.args.get('orphan_entities', [])}\n"
                f"Sample orphan triples (broken refs): {step.args.get('orphan_triples', [])}\n\n"
                "Propose 'clean' actions for orphans that should be archived, "
                "and 'insight' notes for any orphan that suggests a missing "
                "connection rather than dead data."
            )
        if section == "duplicates":
            return (
                common_preamble
                + f"Section: DUPLICATES\n"
                f"Likely duplicate entity groups: {step.args.get('entity_groups', [])}\n"
                f"Likely duplicate closet groups: {step.args.get('closet_groups', [])}\n\n"
                "Propose 'reorganize' actions that merge duplicates. "
                "Each merge proposal must specify the canonical id (the survivor) "
                "and the ids being merged into it."
            )
        if section == "suspicion":
            return (
                common_preamble
                + f"Section: SUSPICION (low-quality triples)\n"
                f"Low confidence: {step.args.get('low_confidence', [])}\n"
                f"Self-referential: {step.args.get('self_referential', [])}\n"
                f"Stoplist-object triples: {step.args.get('stoplist_objects', [])}\n\n"
                "These triples are likely noise. Propose 'clean' actions to "
                "remove or invalidate them, or 'insight' notes if any of them "
                "actually represent a real pattern that should be salvaged."
            )
        return common_preamble + f"Unknown section: {section!r}"
