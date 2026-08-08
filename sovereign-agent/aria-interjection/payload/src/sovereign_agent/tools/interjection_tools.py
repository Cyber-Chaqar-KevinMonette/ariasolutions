"""
tools/interjection_tools.py — Safe BTW/Interjection system (M37).

Four tools for non-interrupting objective management:

  add_objective(text, priority, scope, relate_to)  T1 — inject secondary goal
  btw_note(text, relates_to)                       T1 — lightweight note, no action
  list_objectives(include_completed)               T0 — show active objectives
  complete_objective(objective_id)                 T1 — mark done

Design: Aria sees new objectives at the next iteration start (not immediately).
This preserves active workflow focus. The operator or Aria can inject objectives
at any time; they surface in priority order.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ── add_objective ─────────────────────────────────────────────────────────────


class _AddArgs(BaseModel):
    text: str = Field(description="The objective text. Be specific and actionable.")
    priority: str = Field(
        default="secondary",
        description="Priority: 'primary', 'secondary', or 'background'.",
    )
    scope: str = Field(
        default="this_session",
        description="Scope: 'this_session', 'persistent', or 'this_workflow'.",
    )
    relate_to: Optional[str] = Field(
        default=None,
        description="ID of related objective or workflow this is linked to.",
    )


class AddObjectiveTool(Tool[_AddArgs]):
    name = "add_objective"
    tier = 1
    description = (
        "Inject a secondary objective without interrupting current work. "
        "The objective is parked in the ObjectiveMap and surfaces at the "
        "next natural pause point. Use priority='primary' to front-queue, "
        "'secondary' for important-but-not-urgent, 'background' for opportunistic. "
        "Emits objective-added-d event. Does NOT interrupt active tool chains."
    )
    failure_modes = ("atom_write_failed", "invalid_priority", "invalid_scope")
    Args = _AddArgs

    async def execute(self, args: _AddArgs, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.objective_map import get_objective_map
            from sovereign_agent.config import SETTINGS

            valid_priorities = {"primary", "secondary", "background"}
            valid_scopes = {"this_session", "persistent", "this_workflow"}
            if args.priority not in valid_priorities:
                return ToolResult(ok=False, error=f"invalid priority '{args.priority}'; must be one of {valid_priorities}")
            if args.scope not in valid_scopes:
                return ToolResult(ok=False, error=f"invalid scope '{args.scope}'; must be one of {valid_scopes}")

            obj_map = get_objective_map()
            obj = obj_map.add(
                text=args.text,
                priority=args.priority,  # type: ignore[arg-type]
                scope=args.scope,  # type: ignore[arg-type]
                relate_to=args.relate_to,
            )

            # Write to atoms DB
            atom_id = await asyncio.to_thread(
                _write_objective_atom, obj.as_dict(), trace_id
            )

            return ToolResult(ok=True, output={
                "objective_id": obj.id,
                "text": obj.text,
                "priority": obj.priority,
                "scope": obj.scope,
                "atom_id": atom_id,
                "message": (
                    f"Objective parked ({obj.priority}). "
                    "Will surface at next natural pause."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"add_objective failed: {e}")


# ── btw_note ──────────────────────────────────────────────────────────────────


class _BtwArgs(BaseModel):
    text: str = Field(description="The BTW note. Lightweight — no action required.")
    relates_to: Optional[str] = Field(
        default=None,
        description="Optional ID of related objective or workflow.",
    )


class BtwNoteTool(Tool[_BtwArgs]):
    name = "btw_note"
    tier = 1
    description = (
        "Park a lightweight 'by the way' note without requiring action. "
        "Aria sees it at the next iteration start. Useful for soft observations, "
        "reminders, or context that doesn't need to interrupt the current flow. "
        "Emits btw-note-d event. No action is implied or expected."
    )
    failure_modes = ("atom_write_failed",)
    Args = _BtwArgs

    async def execute(self, args: _BtwArgs, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.objective_map import get_objective_map

            obj_map = get_objective_map()
            obj = obj_map.add_btw(text=args.text, relates_to=args.relates_to)

            atom_id = await asyncio.to_thread(
                _write_objective_atom, obj.as_dict(), trace_id
            )

            return ToolResult(ok=True, output={
                "note_id": obj.id,
                "text": obj.text,
                "atom_id": atom_id,
                "message": "BTW note parked. Surfaces at next iteration start.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"btw_note failed: {e}")


# ── list_objectives ───────────────────────────────────────────────────────────


class _ListArgs(BaseModel):
    include_completed: bool = Field(
        default=False,
        description="Include completed/cancelled objectives in the list.",
    )
    scope: Optional[str] = Field(
        default=None,
        description="Filter by scope ('this_session', 'persistent', 'this_workflow'). Omit for all.",
    )


class ListObjectivesTool(Tool[_ListArgs]):
    name = "list_objectives"
    tier = 0
    description = (
        "List active objectives and BTW notes, sorted by priority. "
        "Call at session start (after aria_status) to surface any parked goals. "
        "Check periodically during long sessions to address secondary objectives "
        "at natural pause points."
    )
    failure_modes = ("objective_map_unavailable",)
    Args = _ListArgs

    async def execute(self, args: _ListArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.objective_map import get_objective_map

            obj_map = get_objective_map()
            objectives = obj_map.by_priority() if not args.include_completed else obj_map.list_active(include_completed=True)

            if args.scope:
                objectives = [o for o in objectives if o.scope == args.scope]

            # Split BTW notes from real objectives
            btw_notes = [o for o in objectives if o.note == "btw"]
            real_objectives = [o for o in objectives if o.note != "btw"]

            return ToolResult(ok=True, output={
                "objectives": [o.as_dict() for o in real_objectives],
                "btw_notes": [o.as_dict() for o in btw_notes],
                "total_active": len(objectives),
                "priority_summary": {
                    "primary": sum(1 for o in real_objectives if o.priority == "primary"),
                    "secondary": sum(1 for o in real_objectives if o.priority == "secondary"),
                    "background": sum(1 for o in real_objectives if o.priority == "background"),
                },
                "note": (
                    "Address primary objectives immediately. Secondary at next pause. "
                    "Background when opportunistic."
                ) if objectives else "No active objectives.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"list_objectives failed: {e}")


# ── complete_objective ────────────────────────────────────────────────────────


class _CompleteArgs(BaseModel):
    objective_id: str = Field(description="The ID of the objective to mark complete.")
    outcome_note: Optional[str] = Field(
        default=None,
        description="Optional note about how the objective was completed.",
    )


class CompleteObjectiveTool(Tool[_CompleteArgs]):
    name = "complete_objective"
    tier = 1
    description = (
        "Mark an objective as complete. Writes the completion to the atom history. "
        "Call when an objective has been fully addressed, even if it was addressed "
        "incidentally while working on something else."
    )
    failure_modes = ("objective_not_found", "atom_write_failed")
    Args = _CompleteArgs

    async def execute(self, args: _CompleteArgs, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.objective_map import get_objective_map

            obj_map = get_objective_map()
            obj = obj_map.complete(args.objective_id)
            if obj is None:
                return ToolResult(ok=False, error=f"objective not found: {args.objective_id}")

            data = obj.as_dict()
            if args.outcome_note:
                data["outcome_note"] = args.outcome_note

            atom_id = await asyncio.to_thread(
                _write_objective_atom, data, trace_id
            )

            return ToolResult(ok=True, output={
                "objective_id": obj.id,
                "text": obj.text,
                "status": "complete",
                "completed_at": obj.completed_at,
                "atom_id": atom_id,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"complete_objective failed: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _write_objective_atom(data: dict, trace_id: str) -> str:
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom

    note_type = data.get("note", "")
    atom_type = "btw-note" if note_type == "btw" else "objective"

    atom = Atom(
        type=atom_type,
        summary=f"[{data.get('priority', 'secondary')}] {data['text'][:200]}",
        content_ref={"kind": "inline", "content": json.dumps(data)},
        claims=[],
        parents=[trace_id],
        confidence=1.0,
        created_by={"actor": "interjection", "version": "M37"},
        scope_tags=["objective"],
    )
    conn = open_atoms_db()
    try:
        aid = write_atom(conn, atom)
        conn.commit()
        return aid
    finally:
        conn.close()


__all__ = [
    "AddObjectiveTool",
    "BtwNoteTool",
    "ListObjectivesTool",
    "CompleteObjectiveTool",
]
