"""tools/inbox_tools.py — Workstream O: give Aria a first-class tool-call
path into the collaboration inbox, in BOTH directions.

Before this, the only way anything got into `RequestStore` was `sov requests
ask` (a CLI command) or the authority gate's own auto-filed pauses — nothing
in `tools/` wrapped `RequestStore.open()`, so Aria had no direct tool-call
path to "send Kevin something." This module closes that gap and adds the
new reverse direction (Kevin -> Aria) Kevin asked for.

  SendToHumanTool  T0 — Aria -> Kevin. Wraps RequestStore.send_to_human().
  ReadInboxTool    T0 — Aria checks what Kevin left FOR her (direction=to_aria).
                        Meant to be called at a safe checkpoint (session
                        start, or right after a paused autonomy interval is
                        resumed) — never mid-task.
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
    note. Shows up in his inbox (`sov requests`, the cockpit inbox pane) for
    him to answer whenever he's next available — not a live interrupt.

    FAILURE MODES: write_error
    """

    name = "send_to_human"
    tier = 0
    description = (
        "File a durable message for Kevin in the collaboration inbox — a "
        "question, suggestion, blocker, or note. He sees it in `sov requests` "
        "or the cockpit inbox pane and answers when he's next available. "
        "Not an interrupt — use this for anything that can wait for a reply."
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

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            rs = _request_store()
            req = rs.send_to_human(
                args.title, kind=args.kind, body=args.body,
                rationale=args.rationale, tags=args.tags, priority=args.priority,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        return ToolResult(
            ok=True,
            output={"request_id": req.request_id, "short_id": req.short_id,
                    "title": req.title, "direction": req.direction},
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
