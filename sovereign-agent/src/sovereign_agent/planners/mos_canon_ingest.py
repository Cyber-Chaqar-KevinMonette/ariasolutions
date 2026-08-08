"""mos-canon-ingest planner: populate room-mos-canon with the Unified MOS
Canon clauses, each framed adaptively.

This is the room you reach for when you need doctrinal guidance on a design
decision. The reflection loop can search this room for relevant patterns
("am I about to violate the priority stack?") and surface them as advisory
context.

Pure-Python execution — no model needed. The clauses live in mos_canon.py
as code; this planner just files them in the palace so they're searchable
through the same surface as everything else.

Idempotent: re-running replaces the room's content (deterministic ids),
so doctrine updates flow through cleanly when mos_canon.py is updated.
"""
from __future__ import annotations

from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class MOSCanonIngestPlanner(Planner):
    name = "mos-canon-ingest"
    description = (
        "Populate room-mos-canon with adaptive doctrine clauses. "
        "Pure-Python, no model. Idempotent."
    )

    def required_args(self) -> tuple[str, ...]:
        return ()

    def plan(self, **kwargs: Any) -> PlanResult:
        from ..mos_canon import ALL_CLAUSES

        if not ALL_CLAUSES:
            raise PlannerError("mos-canon-ingest: no clauses defined in mos_canon.py")

        steps = [
            Step(
                id=i,
                kind="mos_canon_ingest_clause",
                args={"clause_id": c.id},
                required_model="none",
            )
            for i, c in enumerate(ALL_CLAUSES)
        ]
        return PlanResult(
            goal=f"Ingest {len(ALL_CLAUSES)} MOS canon clauses into room-mos-canon",
            steps=steps,
            output_path=None,
            notes="adaptive doctrine; high-leverage patterns, not cages",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        clause_id = step.args.get("clause_id", "(missing)")
        return f"Ingest MOS clause {clause_id} into room-mos-canon."


def execute_mos_canon_ingest_step(step: Step) -> str:
    """Pure-Python executor for one mos_canon_ingest_clause step.

    Looks up the clause in the registry and writes it as a closet in
    room-mos-canon. Adds Entity rows for each related clause. Idempotent
    via deterministic ids.
    """
    from ..mos_canon import ADAPTIVE_FRAMING, get_clause
    from ..palace import Closet, Entity, RoomNotFound, open_palace

    clause_id = step.args.get("clause_id")
    if not clause_id:
        raise ValueError("mos_canon_ingest_clause step missing clause_id")

    clause = get_clause(clause_id)
    if clause is None:
        raise ValueError(f"unknown clause_id: {clause_id}")

    p = open_palace()
    try:
        try:
            p.get_room("room-mos-canon")
        except RoomNotFound:
            p.create_room(
                room_id="room-mos-canon",
                name="Unified MOS Canon (Adaptive)",
                description=ADAPTIVE_FRAMING,
                schema={
                    "kind": "doctrine",
                    "framing": ADAPTIVE_FRAMING,
                    "parts": [
                        "kernel", "workflow", "language",
                        "architecture", "agentic",
                    ],
                },
            )

        # Closet topic carries the adaptive framing in its metadata, not the topic
        # line (keeps topic lines short and searchable).
        topic = clause.to_topic_line()

        # Entities: this clause's related clauses, plus the part name.
        ent_names = list(clause.related) + [f"part:{clause.part}"]

        closet = Closet(
            id=f"closet-mos-{clause.id}",
            room_id="room-mos-canon",
            topic=topic,
            entities=ent_names,
            atom_ids=[],  # canon is not derived from atoms
            embedding=None,
            source_file=None,
        )
        p.add_closet(closet)

        # Upsert an entity for the clause itself, with full metadata
        # in properties.
        p.upsert_entity(Entity(
            id=f"entity-mos-{clause.id}",
            name=clause.title,
            type="mos_clause",
            properties={
                "part": clause.part,
                "principle": clause.principle,
                "leverage": clause.leverage,
                "modulation": clause.modulation,
                "examples": clause.examples,
                "related": clause.related,
                "framing": ADAPTIVE_FRAMING,
            },
        ))

        # Also upsert lightweight entities for related-clause links
        for rel_id in clause.related:
            rel = get_clause(rel_id)
            if rel is not None:
                p.upsert_entity(Entity(
                    id=f"entity-mos-{rel.id}",
                    name=rel.title,
                    type="mos_clause",
                    properties={"part": rel.part},
                ))
    finally:
        p.close()

    return f"ingested clause {clause_id} ({clause.title}) into room-mos-canon"
