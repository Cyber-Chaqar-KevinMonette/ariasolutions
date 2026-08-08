"""
lessons_tool.py — Tier 0: read lessons distilled by the Reflector

The Reflector fires after every completed or failed task and distills ONE
durable lesson into the ``lessons`` table in atoms.db. This tool reads
those lessons so Aria can apply accumulated wisdom at the start of each
session.

Lessons schema (from reflector.py):
  lesson_id, ts, trigger, context, failure_mode, correction, rule,
  evidence_refs (JSON), confidence

Read at session start via boot sequence. Filter by topic for focused recall.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class ReadLessonsTool(Tool):
    """Read lessons distilled by the Reflector after past task sessions.

    The Reflector writes one lesson per completed task. This tool surfaces
    the most recent lessons so Aria can apply accumulated wisdom before
    starting new work.

    Call this at the start of every session (it's in the KNOW THYSELF boot
    sequence). Call it again when starting a complex task to check for
    relevant prior learnings.
    """

    name = "read_lessons"
    tier = 0
    description = (
        "Read lessons distilled by the Reflector after past task sessions. "
        "Args: limit (default 10, max 50), topic (optional keyword filter on rule/trigger). "
        "Returns: formatted list of lessons with timestamp, rule, correction, and confidence. "
        "Call at session start to apply accumulated wisdom. "
        "FAILURE MODES: db_not_found, db_error, no_lessons_yet."
    )
    failure_modes = ("db_not_found", "db_error", "no_lessons_yet")

    class Args(BaseModel):
        limit: int = Field(default=10, ge=1, le=50, description="Max lessons to return (most recent first).")
        topic: str = Field(default="", description="Optional keyword filter — matched against rule and trigger text.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.db import open_atoms_db
        except ImportError:
            return ToolResult(ok=False, error="db module not found — atoms.db may not be initialized")

        try:
            conn = open_atoms_db()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"could not open atoms.db: {exc!r}")

        try:
            # Build query
            if args.topic:
                like = f"%{args.topic}%"
                rows = conn.execute(
                    "SELECT lesson_id, ts, trigger, context, failure_mode, correction, rule, confidence "
                    "FROM lessons "
                    "WHERE rule LIKE ? OR trigger LIKE ? OR context LIKE ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (like, like, like, args.limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT lesson_id, ts, trigger, context, failure_mode, correction, rule, confidence "
                    "FROM lessons "
                    "ORDER BY ts DESC LIMIT ?",
                    (args.limit,),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            conn.close()
            return ToolResult(ok=False, error=f"db query failed: {exc!r}")
        finally:
            conn.close()

        if not rows:
            qualifier = f" matching '{args.topic}'" if args.topic else ""
            return ToolResult(
                ok=True,
                output=f"No lessons{qualifier} yet. The Reflector writes lessons after each completed task.",
                metadata={"count": 0},
            )

        # Format
        lines = [f"═══ {len(rows)} Recent Lessons ═══", ""]
        for i, row in enumerate(rows, 1):
            lesson_id, ts, trigger, context, failure_mode, correction, rule, confidence = row
            # Parse timestamp
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_short = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                ts_short = str(ts)[:16]

            conf_pct = f"{float(confidence or 0)*100:.0f}%"
            fail_note = f"  failure: {failure_mode}" if failure_mode else ""
            lines += [
                f"[{i}] {ts_short}  confidence: {conf_pct}",
                f"    RULE: {rule}",
                f"    correction: {correction}",
                f"    trigger: {trigger}",
            ]
            if fail_note:
                lines.append(f"   {fail_note}")
            lines.append("")

        if args.topic:
            lines.insert(1, f"(filtered by: '{args.topic}')")
            lines.insert(2, "")

        return ToolResult(
            ok=True,
            output="\n".join(lines).rstrip(),
            metadata={
                "count": len(rows),
                "topic": args.topic,
                "limit": args.limit,
            },
        )
