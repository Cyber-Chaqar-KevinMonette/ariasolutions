"""event_log_tool.py — Tier 1: give Aria her OWN hands on the sub-event
system, not just infrastructure only Python code could reach.

Kevin, 2026-07-21: "make the sub event system where she can intelligently
call on other events she can send a queue of events to be used." The
mechanism (events.emit_child_event / event_children / event_tree) already
existed as plain Python helpers after the events-hardening round earlier
this session — this is the tool surface so SHE can use it mid-session:

  log_events   — emit a QUEUE of related sub-events in one call, all
                 children of one parent (or chained to each other),
                 returning their event_ids so she can reference them
                 later or nest a further level under any one of them.
  read_events  — "call on other events": look up the children already
                 recorded under a parent_id she remembers, or under her
                 own current session/subtask trace_id.

Tier 1 (not 0): writing to the durable event log is a real, if small,
side effect, and read_events touches the SQLite projection — matches
memory_write's own tier for the same reason (durable-store write).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_MAX_QUEUE = 20  # a deliberate, small, bounded batch — not unlimited


class _LogEventEntry(BaseModel):
    flag: str = Field(description="Event flag name, e.g. 'plan-step-d'.")
    note: str = Field(default="", max_length=500,
                       description="Short human-readable note for this sub-event.")


class _LogEventsArgs(BaseModel):
    trace_id: str = Field(description="The trace_id to file these under "
                                       "(usually the current session_id).")
    events: list[_LogEventEntry] = Field(
        min_length=1, max_length=_MAX_QUEUE,
        description=f"A queue of up to {_MAX_QUEUE} sub-events to emit in order.",
    )
    parent_id: str | None = Field(
        default=None,
        description="Optional event_id these all become children of "
                     "(e.g. a subtask-start-d id from earlier in this run). "
                     "Omit to emit them as top-level events instead.",
    )
    chain: bool = Field(
        default=False,
        description="If true, each event after the first becomes a "
                     "child of the ONE BEFORE IT instead of all sharing "
                     "the same parent_id — use this for a sequence of "
                     "steps where each genuinely follows from the last.",
    )


class LogEventsTool(Tool[_LogEventsArgs]):
    name = "log_events"
    tier = 1
    description = (
        "Emit a queue of related sub-events in one call — e.g. the steps "
        "you're about to take on a subtask, so they're recorded as a "
        "real, queryable tree (not just something you said in chat). "
        "Args: trace_id, events (list of {flag, note}, up to "
        f"{_MAX_QUEUE}), parent_id (optional — nest under an earlier "
        "event_id you remember), chain (optional — link each event to "
        "the one before it instead of a shared parent). Returns the "
        "list of event_ids created, in order — reuse one as a parent_id "
        "to nest a further level under it later. "
        "FAILURE MODES: empty_queue, too_many_events, write_failed."
    )
    failure_modes = ("empty_queue", "too_many_events", "write_failed")
    Args = _LogEventsArgs

    async def execute(self, args: _LogEventsArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from ..events import emit_child_event, emit_event

        try:
            event_ids: list[str] = []
            parent = args.parent_id
            for entry in args.events:
                payload = {"note": entry.note} if entry.note else {}
                if parent:
                    eid = emit_child_event(
                        entry.flag, plane="agent", trace_id=args.trace_id,
                        parent_id=parent, payload=payload,
                    )
                else:
                    eid = emit_event(
                        entry.flag, plane="agent", trace_id=args.trace_id,
                        payload=payload,
                    )
                event_ids.append(eid)
                if args.chain:
                    parent = eid
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_failed: {e}")

        return ToolResult(
            ok=True,
            output={"event_ids": event_ids, "count": len(event_ids)},
            metadata={"count": len(event_ids)},
        )


class _ReadEventsArgs(BaseModel):
    parent_id: str = Field(description="An event_id whose children you want to see.")
    limit: int = Field(default=20, ge=1, le=100,
                       description="Max children to return, oldest first.")


class ReadEventsTool(Tool[_ReadEventsArgs]):
    name = "read_events"
    tier = 1
    description = (
        "Look up every sub-event recorded as a child of a given "
        "event_id — 'call on other events' you (or an earlier subtask) "
        "already logged, instead of relying on memory of the chat. "
        "Args: parent_id (an event_id from an earlier subtask-start-d, "
        "or one you got back from log_events), limit (default 20). "
        "Returns each child's flag, ts, and payload. "
        "FAILURE MODES: no_children_found (not an error — just empty)."
    )
    failure_modes = ("no_children_found",)
    Args = _ReadEventsArgs

    async def execute(self, args: _ReadEventsArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from ..events import event_children, init_events_db, tail_to_sqlite

        try:
            conn = init_events_db()
            try:
                tail_to_sqlite(conn)  # make sure recent writes are visible
                children = event_children(args.parent_id, conn=conn)[:args.limit]
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"query_failed: {e}")

        return ToolResult(
            ok=True,
            output={
                "children": [
                    {"event_id": c["event_id"], "flag": c["flag"],
                     "ts": c["ts"], "payload": c["payload"]}
                    for c in children
                ],
                "count": len(children),
            },
            metadata={"count": len(children)},
        )


__all__ = ["LogEventsTool", "ReadEventsTool"]
