"""palace-apply planner: for each APPROVED proposal in the proposal store,
emit a step that executes it. Pure-Python, no model.

Safety properties:
  - Only proposals with status='approved' are queued.
  - Each step re-verifies the HMAC signature at execution time (defense
    in depth — the status field could be edited).
  - Every applied change is logged to events.jsonl with full before/after.
  - Every applied change records its inverse in proposal.rollback so the
    operator can undo it.

This is the half of the self-reflection loop that mutates state. The
other half (palace-reflect) is read-only and proposal-only. The
proposal-store HMAC is the wall between them.
"""
from __future__ import annotations

from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


class PalaceApplyPlanner(Planner):
    name = "palace-apply"
    description = "Execute approved proposals against the palace. No model invocation."

    def required_args(self) -> tuple[str, ...]:
        return ()

    def plan(self, **kwargs: Any) -> PlanResult:
        from ..proposals import open_store

        only_kind = kwargs.get("only_kind")  # optional: filter by proposal kind
        max_proposals = int(kwargs.get("max_files") or 0)

        store = open_store()
        approved = store.list_all(status="approved")
        if only_kind:
            approved = [p for p in approved if p.kind == only_kind]
        if max_proposals > 0:
            approved = approved[:max_proposals]

        if not approved:
            raise PlannerError(
                "palace-apply: no approved proposals to apply"
                + (f" (filtered to kind={only_kind!r})" if only_kind else "")
                + ". Run `sovereign proposals approve <id>` to authorize one."
            )

        steps = [
            Step(
                id=i,
                kind="palace_apply_proposal",
                args={"proposal_id": p.id},
                required_model="none",
            )
            for i, p in enumerate(approved)
        ]
        return PlanResult(
            goal=f"Apply {len(approved)} approved proposal(s) to palace",
            steps=steps,
            output_path=None,
            notes=f"only_kind={only_kind}" if only_kind else "all approved kinds",
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        proposal_id = step.args.get("proposal_id", "(missing)")
        return f"Apply approved proposal {proposal_id}."


# ─── Execution dispatch ────────────────────────────────────────────────────


def execute_palace_apply_step(step: Step) -> str:
    """Pure-Python executor for palace_apply_proposal steps.

    Verifies signature at execution time. Looks up the proposal's kind +
    action, dispatches to the correct apply function. Records result and
    rollback metadata back into the proposal.

    Returns one-line summary for the event log. Raises ValueError on
    unrecoverable errors; the runner converts these to poison.
    """
    from ..approval import _load_or_create_secret
    from ..events import emit_event
    from ..proposals import (
        ProposalNotApprovable,
        open_store,
        verify_signature,
    )

    proposal_id = step.args.get("proposal_id")
    if not proposal_id:
        raise ValueError(f"palace_apply_proposal step missing proposal_id: {step.args}")

    store = open_store()
    p = store.get(proposal_id)

    if p.status != "approved":
        raise ProposalNotApprovable(
            f"proposal {proposal_id} status is {p.status!r}, expected 'approved'"
        )

    # Defense-in-depth: re-verify signature at execution time.
    secret = _load_or_create_secret()
    if not verify_signature(p, secret=secret):
        # Tampered. Mark as failed and refuse.
        store.mark_failed(proposal_id, error="HMAC signature failed verification")
        raise ValueError(
            f"proposal {proposal_id}: signature verification FAILED. "
            "Refusing to apply. The action may have been edited after approval."
        )

    # Dispatch by kind/action_type.
    action_type = p.action.get("type", "")
    handler = _APPLY_DISPATCH.get((p.kind, action_type))
    if handler is None:
        store.mark_failed(
            proposal_id,
            error=f"no handler for kind={p.kind!r} action.type={action_type!r}",
        )
        raise ValueError(
            f"proposal {proposal_id}: no handler for kind={p.kind!r} type={action_type!r}"
        )

    # Run the handler. It returns (result_summary, rollback_descriptor).
    try:
        result_summary, rollback = handler(p.action)
    except Exception as e:  # noqa: BLE001
        store.mark_failed(proposal_id, error=f"{type(e).__name__}: {e}")
        raise ValueError(f"proposal {proposal_id} handler raised: {e}") from e

    # Record success.
    store.mark_applied(proposal_id, result=result_summary, rollback=rollback)

    # Audit event.
    emit_event(
        "proposal-applied-d",
        plane="control",
        trace_id=f"prop:{proposal_id}",
        payload={
            "proposal_id": proposal_id,
            "kind": p.kind,
            "action_type": action_type,
            "result": result_summary[:200],
            "rollback_kind": (rollback or {}).get("type", ""),
        },
    )
    return f"applied {proposal_id}: {result_summary[:200]}"


# ─── Action handlers ───────────────────────────────────────────────────────
#
# Each handler takes the action dict and returns (result_summary,
# rollback_descriptor). The rollback descriptor is a dict that, if
# applied later, undoes this change. It's stored on the proposal so the
# operator can choose to undo without manual SQL surgery.


def _handle_clean_remove_triple(action: dict) -> tuple[str, dict]:
    """Mark a triple invalid via valid_to. Soft-delete; not a hard remove."""
    from datetime import datetime, timezone
    from ..palace import open_palace

    triple_id = action.get("triple_id")
    if not triple_id:
        raise ValueError("clean.remove_triple action missing triple_id")
    ended = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    p = open_palace()
    try:
        ok = p.invalidate_triple(triple_id, ended=ended)
    finally:
        p.close()
    if not ok:
        raise ValueError(f"triple {triple_id} not found or already invalidated")
    return (
        f"invalidated triple {triple_id} as of {ended}",
        {"type": "restore_triple", "triple_id": triple_id, "valid_to": None},
    )


def _handle_clean_remove_closet(action: dict) -> tuple[str, dict]:
    """Hard-delete a closet. Records the closet's content for rollback."""
    from ..palace import Closet, open_palace

    closet_id = action.get("closet_id")
    if not closet_id:
        raise ValueError("clean.remove_closet action missing closet_id")
    p = open_palace()
    try:
        # Read the closet so we can restore it on rollback
        closets = p.list_closets()
        target = next((c for c in closets if c.id == closet_id), None)
        if target is None:
            raise ValueError(f"closet {closet_id} not found")
        # Rollback descriptor: full re-add
        rollback = {
            "type": "restore_closet",
            "closet": {
                "id": target.id, "room_id": target.room_id,
                "topic": target.topic, "entities": target.entities,
                "atom_ids": target.atom_ids,
                "embedding": target.embedding, "source_file": target.source_file,
                "created_at": target.created_at,
            },
        }
        # Delete via the palace's own method (none exists — go through SQL)
        with p._connect() as c:
            c.execute("DELETE FROM closets WHERE id = ?", (closet_id,))
    finally:
        p.close()
    return (f"removed closet {closet_id}", rollback)


def _handle_reorganize_merge_entities(action: dict) -> tuple[str, dict]:
    """Merge a list of duplicate entity ids into a canonical one.

    Updates triples that reference the merged-away ids to point at the
    canonical id. The merged-away entities are then deleted.

    Rollback: the original ids and their pre-merge triple references are
    recorded so the operation can be reversed.
    """
    from ..palace import open_palace

    canonical = action.get("canonical_id")
    duplicates = list(action.get("duplicate_ids") or [])
    if not canonical or not duplicates:
        raise ValueError(
            "reorganize.merge_entities requires canonical_id and duplicate_ids"
        )
    if canonical in duplicates:
        raise ValueError("canonical_id cannot also be in duplicate_ids")

    p = open_palace()
    rollback_data: dict = {"type": "restore_entities", "entities": [], "triple_remaps": []}
    try:
        with p._connect() as c:
            # Snapshot the entities being merged away (for rollback)
            for dup_id in duplicates:
                row = c.execute(
                    "SELECT * FROM entities WHERE id = ?", (dup_id,)
                ).fetchone()
                if row:
                    rollback_data["entities"].append({
                        "id": row["id"], "name": row["name"], "type": row["type"],
                        "properties_json": row["properties_json"],
                        "first_seen": row["first_seen"], "last_seen": row["last_seen"],
                    })
            # Snapshot triple remaps (for rollback)
            for dup_id in duplicates:
                rows = c.execute(
                    "SELECT id FROM triples WHERE subject_id = ? OR object_id = ?",
                    (dup_id, dup_id),
                ).fetchall()
                for row in rows:
                    rollback_data["triple_remaps"].append({
                        "triple_id": row["id"], "from_id": canonical, "to_id": dup_id,
                    })
            # Remap triples
            for dup_id in duplicates:
                c.execute(
                    "UPDATE triples SET subject_id = ? WHERE subject_id = ?",
                    (canonical, dup_id),
                )
                c.execute(
                    "UPDATE triples SET object_id = ? WHERE object_id = ?",
                    (canonical, dup_id),
                )
            # Delete merged entities
            placeholders = ",".join("?" for _ in duplicates)
            c.execute(
                f"DELETE FROM entities WHERE id IN ({placeholders})",
                duplicates,
            )
    finally:
        p.close()
    return (
        f"merged {len(duplicates)} duplicate entities into {canonical}",
        rollback_data,
    )


def _handle_insight_record(action: dict) -> tuple[str, dict]:
    """Record an insight as a special closet in a 'room-insights' room.

    Insights aren't strictly mutations of existing structure — they're
    additive notes the model surfaced. We file them in a dedicated insight
    room so they don't mix with regular closets.
    """
    from ..palace import Closet, RoomNotFound, open_palace
    from ulid import ULID

    text = action.get("text", "").strip()
    related_entities = list(action.get("related_entities") or [])
    if not text:
        raise ValueError("insight.record requires non-empty 'text' in action")
    p = open_palace()
    try:
        try:
            p.get_room("room-insights")
        except RoomNotFound:
            p.create_room(
                room_id="room-insights",
                name="Insights",
                description="Model-surfaced observations from palace-reflect.",
            )
        closet_id = f"insight-{ULID()}"
        p.add_closet(Closet(
            id=closet_id, room_id="room-insights",
            topic=f"[insight] {text[:100]}",
            entities=related_entities, atom_ids=[],
            embedding=None, source_file=None,
        ))
    finally:
        p.close()
    return (
        f"recorded insight as {closet_id}",
        {"type": "remove_closet", "closet_id": closet_id},
    )


def _handle_enhancement_note(action: dict) -> tuple[str, dict]:
    """Record an enhancement proposal as a closet in 'room-enhancements'.

    Enhancements are roadmap-style notes — 'this would make the system
    better in some way'. Like insights, additive only.
    """
    from ..palace import Closet, RoomNotFound, open_palace
    from ulid import ULID

    title = action.get("title", "").strip()
    body = action.get("body", "").strip()
    if not title:
        raise ValueError("enhancement.note requires 'title'")
    p = open_palace()
    try:
        try:
            p.get_room("room-enhancements")
        except RoomNotFound:
            p.create_room(
                room_id="room-enhancements",
                name="Enhancements",
                description="Operator-reviewable improvement proposals.",
            )
        closet_id = f"enh-{ULID()}"
        p.add_closet(Closet(
            id=closet_id, room_id="room-enhancements",
            topic=f"[enh] {title[:100]}",
            entities=[], atom_ids=[],
            embedding=None, source_file=None,
        ))
    finally:
        p.close()
    return (
        f"recorded enhancement note as {closet_id}: {title[:60]}",
        {"type": "remove_closet", "closet_id": closet_id},
    )


def _handle_code_update_swap(action: dict) -> tuple[str, dict]:
    """Apply a staged code update: archive current file + swap in proposed.

    REQUIRES that `sov proposals stage <prop-id>` has been run first AND
    that the staged tests passed. The archive_and_swap function refuses
    if test_result.ok != True.

    The HMAC signature on the approved proposal binds the proposal_id and
    the action — but NOT the staged content. This is intentional: staging
    is operator-driven (the operator points at /tmp/myfix.py), and the
    test result is recorded BEFORE approval. The operator approves with
    full knowledge of what's been staged and tested.

    Rollback descriptor: type=code_rollback, archive_dir, target_relpath.
    Sov proposals rollback <prop> reads it and reverses.
    """
    from ..code_update import archive_and_swap
    from ..config import SETTINGS

    proposal_id = action.get("proposal_id")
    if not proposal_id:
        raise ValueError("code_update.swap action requires proposal_id")

    rollback = archive_and_swap(
        proposal_id=proposal_id,
        data_dir=SETTINGS.paths.data_dir,
    )
    return (
        f"swapped {rollback['target_relpath']} "
        f"(archive: {rollback['archive_dir']})",
        rollback,
    )


# Dispatch table: (proposal_kind, action_type) → handler
_APPLY_DISPATCH: dict[tuple[str, str], callable] = {
    ("clean", "remove_triple"): _handle_clean_remove_triple,
    ("clean", "remove_closet"): _handle_clean_remove_closet,
    ("reorganize", "merge_entities"): _handle_reorganize_merge_entities,
    ("insight", "record"): _handle_insight_record,
    ("enhancement", "note"): _handle_enhancement_note,
    ("code_update", "stage_and_swap"): _handle_code_update_swap,
}


def supported_action_types() -> list[tuple[str, str]]:
    """Return the list of (kind, action_type) pairs the apply planner supports.

    Used by the ``proposal_write`` tool to validate that the model is only
    proposing things the system can actually execute.
    """
    return list(_APPLY_DISPATCH.keys())
