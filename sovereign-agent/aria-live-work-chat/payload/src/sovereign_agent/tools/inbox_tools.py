"""tools/inbox_tools.py — Workstream O: give Aria a first-class tool-call
path into the collaboration inbox, in BOTH directions.

Before this, the only way anything got into `RequestStore` was `sov requests
ask` (a CLI command) or the authority gate's own auto-filed pauses — nothing
in `tools/` wrapped `RequestStore.open()`, so Aria had no direct tool-call
path to "send Kevin something." This module closes that gap and adds the
new reverse direction (Kevin -> Aria) Kevin asked for.

  SendToHumanTool       T0 — Aria -> Kevin. Wraps RequestStore.send_to_human().
  ReadInboxTool         T0 — Aria checks what Kevin left FOR her (direction=to_aria).
                             Meant to be called at a safe checkpoint (session
                             start, or right after a paused autonomy interval is
                             resumed) — never mid-task.
  AcknowledgeInboxTool  T0 — Aria closes a to_aria note once she's actually
                             acted on it (Kevin, 2026-07-26: "she needs to be
                             emptying her inbox... keep her inbox empty").
                             Without this, read_inbox had no way to ever
                             shrink the open list — reading isn't resolving.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _request_store():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore
    return RequestStore(ErebloStore(SETTINGS.paths.atoms_db))


# ── SendToHumanTool ─────────────────────────────────────────────────────────


class SendToHumanTool(Tool):
    """Send Kevin something durable — a question, a suggestion, a blocker, a
    note. It is persisted in his inbox and, by default, also appears in the
    cockpit's live chat while work continues.

    FAILURE MODES: write_error
    """

    name = "send_to_human"
    tier = 0
    description = (
        "Send Kevin a durable message during work. By default it appears in "
        "the cockpit live chat within a second and is retained in the "
        "collaboration inbox. It never interrupts an in-flight tool call; "
        "use it for progress, questions, blockers, or decisions."
    )
    failure_modes = ("write_error",)

    class Args(BaseModel):
        title: str = Field(description="Short summary — the WHAT.")
        kind: str = Field(
            default="note",
            description="question|suggestion|blocker|decision|note|celebrate|research",
        )
        body: str = Field(default="", description="Longer detail.")
        rationale: str = Field(default="", description="WHY — the reasoning behind it.")
        priority: str = Field(default="normal", description="low|normal|high|urgent.")
        tags: list[str] = Field(default_factory=list)
        live_chat: bool = Field(
            default=True,
            description="Also show this message in the cockpit live chat immediately.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            rs = _request_store()
            tags = list(args.tags)
            if args.live_chat and "live-chat" not in tags:
                tags.append("live-chat")
            req = rs.send_to_human(
                args.title, kind=args.kind, body=args.body,
                rationale=args.rationale, tags=tags, priority=args.priority,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        return ToolResult(
            ok=True,
            output={"request_id": req.request_id, "short_id": req.short_id,
                    "title": req.title, "direction": req.direction,
                    "live_chat": args.live_chat},
        )


# ── ReadInboxTool ───────────────────────────────────────────────────────────


class ReadInboxTool(Tool):
    """Check what Kevin has left FOR Aria — notes filed with `sov requests
    tell`. Call this at a safe checkpoint (session start, or right after
    resuming from a paused autonomy interval), not mid-task — this mirrors
    how AutonomySession/interrupts.py already treat checkpoints as the only
    safe place to pick up new instructions.

    FAILURE MODES: read_error
    """

    name = "read_inbox"
    tier = 0
    description = (
        "Read open notes Kevin has left for Aria (direction=to_aria) via "
        "`sov requests tell`. Call at a safe checkpoint — session start, or "
        "right after resuming a paused autonomy interval — not mid-task."
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        limit: int = Field(default=20, ge=1, le=200)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            rs = _request_store()
            items = rs.list_for_aria()[: args.limit]
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(
            ok=True,
            output={
                "count": len(items),
                "notes": [
                    {
                        "request_id": r.request_id, "short_id": r.short_id,
                        "title": r.title, "body": r.body,
                        "priority": r.priority, "tags": r.tags,
                        "created_at": r.created_at,
                    }
                    for r in items
                ],
            },
        )


# ── AcknowledgeInboxTool ─────────────────────────────────────────────────────


class AcknowledgeInboxTool(Tool):
    """Close a to_aria note once Aria has actually acted on it.

    read_inbox only reads — nothing ever shrank the open list, so "keep
    your inbox empty" had no real mechanism behind it. Call this AFTER
    you've genuinely handled a note (not as a substitute for handling it).

    FAILURE MODES: not_found, write_error
    """

    name = "acknowledge_inbox_note"
    tier = 0
    description = (
        "Mark a note Kevin left for you (from read_inbox) as handled, so "
        "it leaves your open inbox. Accepts the request_id or short_id. "
        "Call this only after you've actually acted on the note — reading "
        "it alone doesn't close it."
    )
    failure_modes = ("not_found", "write_error")

    class Args(BaseModel):
        request_id: str = Field(
            description="The request_id or short_id from read_inbox's output.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            rs = _request_store()
            req = rs.get(args.request_id)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        if req is None:
            return ToolResult(ok=False, error="not_found: no such request_id")
        try:
            resolved = rs.resolve(req.request_id)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        return ToolResult(
            ok=True,
            output={"request_id": resolved.request_id, "short_id": resolved.short_id,
                    "title": resolved.title, "status": resolved.status},
        )
