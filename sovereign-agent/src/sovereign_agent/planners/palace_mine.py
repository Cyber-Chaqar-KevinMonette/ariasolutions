"""Palace-mine planner: walk atoms.db, extract structured signals from each
atom's summary, write closets + entities + triples into palace.db.

Tagged with ``required_model='none'`` — pure-Python execution, no LLM call.
The ``palace_mining`` module does all the work via curated regex extractors.

Each step processes ONE atom: read summary → mine → write to palace.

    sovereign plan palace-mine \\
        --room-id room-research \\
        --room-name "Research Notes" \\
        --max-files 1000

This makes the Palace populated, queryable, and observable. Run it after
your inventory passes have produced atoms; rerun any time atoms grow.
Idempotent: deterministic ids mean re-mining the same atom produces the
same closet + same triples (INSERT OR REPLACE updates in place).
"""
from __future__ import annotations

from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class PalaceMinePlanner(Planner):
    name = "palace-mine"
    description = "Walk atoms.db, extract closets+entities+triples into palace.db. No model."

    def required_args(self) -> tuple[str, ...]:
        # room_id + room_name are required so we know where to file the closets.
        return ("room_id", "room_name")

    def plan(self, **kwargs: Any) -> PlanResult:
        room_id = kwargs.get("room_id")
        room_name = kwargs.get("room_name")
        max_atoms = int(kwargs.get("max_files") or 0)
        atom_type_filter = kwargs.get("atom_type")  # optional

        if not room_id:
            raise PlannerError("palace-mine: 'room_id' is required")
        if not room_name:
            raise PlannerError("palace-mine: 'room_name' is required")

        # Late imports — keep the planner module light to import.
        from ..db import open_atoms_db
        from ..palace import open_palace, RoomNotFound

        # Ensure the room exists; create if needed.
        palace = open_palace()
        try:
            try:
                palace.get_room(room_id)
            except RoomNotFound:
                palace.create_room(room_id=room_id, name=room_name,
                                   description="auto-created by palace-mine planner")
        finally:
            palace.close()

        # Read atom ids to mine. Only HEAD atoms (superseded_at IS NULL).
        conn = open_atoms_db()
        try:
            sql = (
                "SELECT atom_id, type FROM atoms "
                "WHERE superseded_at IS NULL "
            )
            params: list = []
            if atom_type_filter:
                sql += "AND type = ? "
                params.append(atom_type_filter)
            sql += "ORDER BY created_at"
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        atom_ids = [r[0] for r in rows]
        if max_atoms > 0:
            atom_ids = atom_ids[:max_atoms]

        if not atom_ids:
            raise PlannerError(
                "palace-mine: no atoms to mine"
                + (f" (filtered by type={atom_type_filter!r})" if atom_type_filter else "")
                + ".\n"
                + "  Hint: atoms.db is empty or fully filtered out.\n"
                + "  To produce atoms, use one of:\n"
                + "    • read-files       — reads files, writes one atom per file (uses orchestrator model)\n"
                + "    • code-inventory   — same, but for code files (uses coder model)\n"
                + "    • summaries-to-atoms — atomize an existing inventory text file (no model needed)\n"
                + "  The 'inventory' planner writes to a TEXT FILE only — not atoms.db.\n"
                + "  If you ran 'inventory' already, run 'summaries-to-atoms --output <path>' to salvage."
            )

        steps = [
            Step(
                id=i,
                kind="palace_mine_atom",
                args={"atom_id": atom_id, "room_id": room_id},
                required_model="none",
            )
            for i, atom_id in enumerate(atom_ids)
        ]
        notes = f"room_id={room_id}"
        if atom_type_filter:
            notes += f" type={atom_type_filter}"

        return PlanResult(
            goal=f"Mine {len(atom_ids)} atoms → palace room {room_id}",
            steps=steps,
            output_path=None,  # closets/triples land in palace.db, not a file
            notes=notes,
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        atom_id = step.args.get("atom_id", "(missing)")
        room_id = step.args.get("room_id", "(missing)")
        return f"Mine atom {atom_id} into palace room {room_id}."


def execute_palace_mine_step(step: Step) -> str:
    """Pure-Python execution of a palace_mine_atom step. v0.2.8.

    Called by the runner when ``step.required_model == 'none'`` and
    ``step.kind == 'palace_mine_atom'``. Reads the atom's summary,
    mines it via the regex extractors, and writes the resulting
    closet + entities + triples into palace.db.

    Returns a one-line summary of what got written, suitable for the
    event log. Raises on unrecoverable errors (atom missing, palace
    write failure) — the runner converts these into poison results.
    """
    from ..db import open_atoms_db
    from ..palace import (
        Closet, Entity, Triple, open_palace,
    )
    from ..palace_mining import (
        closet_id_for_atom,
        entity_id_for_name,
        mine_atom,
        triple_id_for,
    )

    atom_id = step.args.get("atom_id")
    room_id = step.args.get("room_id")
    if not atom_id or not room_id:
        raise ValueError(f"palace_mine_atom step missing args: {step.args}")

    # Read atom summary from atoms.db (read-only for this step).
    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT summary, type, scope_path FROM atoms WHERE atom_id = ?",
            (atom_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise ValueError(f"atom {atom_id!r} not found in atoms.db")

    summary, atom_type, scope_path = row[0], row[1], row[2]
    if not summary:
        # Empty summary — nothing to mine. Not an error; return cleanly.
        return f"atom {atom_id}: empty summary, skipped"

    # Run the extractors. Pure function, no I/O.
    mined = mine_atom(atom_id, summary)

    # Write closet + entities + triples into palace.db.
    palace = open_palace()
    try:
        # Closet — one per atom, deterministic id.
        closet = Closet(
            id=closet_id_for_atom(atom_id),
            room_id=room_id,
            topic=mined.topic,
            entities=mined.entities,
            atom_ids=[atom_id],
            embedding=None,  # v0.2.9 candidate: embed via embed_query tool
            source_file=scope_path,
        )
        palace.add_closet(closet)

        # Entities — upsert each detected entity.
        entity_ids: dict[str, str] = {}
        for ent_name in mined.entities:
            eid = entity_id_for_name(ent_name)
            entity_ids[ent_name] = eid
            palace.upsert_entity(Entity(
                id=eid, name=ent_name,
                type="auto",  # heuristic: caller can refine
                properties={"atom_type": atom_type or "unknown"},
            ))

        # Triples — write each extracted triple.
        triple_count = 0
        for et in mined.triples:
            subj_id = entity_ids.get(et.subject) or entity_id_for_name(et.subject)
            # If subject wasn't in our entity list, register it now.
            if et.subject not in entity_ids:
                palace.upsert_entity(Entity(id=subj_id, name=et.subject, type="auto"))
                entity_ids[et.subject] = subj_id

            # Object: if it matches an entity, use object_id; else literal.
            obj_id_or_lit = entity_ids.get(et.object)
            if obj_id_or_lit:
                triple = Triple(
                    id=triple_id_for(subj_id, et.predicate, obj_id_or_lit),
                    subject_id=subj_id,
                    predicate=et.predicate,
                    object_id=obj_id_or_lit,
                    confidence=et.confidence,
                    source_atom_ids=[atom_id],
                    source_closet_id=closet.id,
                )
            else:
                triple = Triple(
                    id=triple_id_for(subj_id, et.predicate, et.object),
                    subject_id=subj_id,
                    predicate=et.predicate,
                    object_literal=et.object,
                    confidence=et.confidence,
                    source_atom_ids=[atom_id],
                    source_closet_id=closet.id,
                )
            palace.add_triple(triple)
            triple_count += 1
    finally:
        palace.close()

    # One-line summary for the event log
    mt_summary = ",".join(m.memory_type for m in mined.memory_types) or "none"
    return (
        f"atom {atom_id}: closet={closet.id} "
        f"entities={len(mined.entities)} "
        f"types={mt_summary} "
        f"triples={triple_count}"
    )
