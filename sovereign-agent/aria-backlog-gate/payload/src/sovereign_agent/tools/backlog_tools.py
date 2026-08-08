"""tools/backlog_tools.py — Backlog read + quality gate tools (M60).

  backlog_read()    T0 — read backlog.yaml, return pending/running/done/flagged counts
  backlog_gate()    T1 — run BacklogGate over pending tasks, write flagged status back
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.mode_controller import read_backlog, write_backlog, BacklogTask
except ImportError:
    read_backlog = None  # type: ignore[assignment]
    write_backlog = None  # type: ignore[assignment]
    BacklogTask = None  # type: ignore[assignment]

try:
    from sovereign_agent.backlog_gate import BacklogGate
except ImportError:
    BacklogGate = None  # type: ignore[assignment]


# ── BacklogReadTool ───────────────────────────────────────────────────────────

class _ReadArgs(BaseModel):
    include_done: bool = Field(default=False, description="Include done/halted tasks in output.")
    limit: int = Field(default=20, ge=1, le=100, description="Max pending tasks to list.")


class BacklogReadTool(Tool[_ReadArgs]):
    name = "backlog_read"
    tier = 0
    description = (
        "Read backlog.yaml and return pending/running/done/flagged task counts "
        "plus the list of pending tasks. "
        "Use to understand what's queued before an auto session."
    )
    failure_modes = ("backlog_unavailable",)
    Args = _ReadArgs

    async def execute(self, args: _ReadArgs, *, trace_id: str) -> ToolResult:
        if read_backlog is None:
            return ToolResult(ok=True, output={
                "pending_count": 0, "running_count": 0, "done_count": 0,
                "flagged_count": 0, "total": 0, "pending": [],
                "note": "read_backlog unavailable",
            })
        try:
            tasks = await asyncio.to_thread(read_backlog)
            counts = {"pending": 0, "running": 0, "done": 0, "flagged": 0, "other": 0}
            for t in tasks:
                status = t.status.lower()
                if status in counts:
                    counts[status] += 1
                else:
                    counts["other"] += 1

            pending = [
                {"id": t.id, "goal": t.goal, "priority": t.priority, "mode": t.mode}
                for t in tasks if t.status == "pending"
            ][:args.limit]

            output = {
                "pending_count": counts["pending"],
                "running_count": counts["running"],
                "done_count": counts["done"],
                "flagged_count": counts["flagged"],
                "total": len(tasks),
                "pending": pending,
            }
            if args.include_done:
                done = [
                    {"id": t.id, "goal": t.goal[:80], "status": t.status}
                    for t in tasks if t.status in ("done", "halted", "budget", "poison")
                ]
                output["completed"] = done

            return ToolResult(ok=True, output=output)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"backlog_read failed: {e}")


# ── BacklogGateTool ───────────────────────────────────────────────────────────

class _GateArgs(BaseModel):
    dry_run: bool = Field(
        default=True,
        description="If True, report findings without writing to backlog.yaml.",
    )


class BacklogGateTool(Tool[_GateArgs]):
    name = "backlog_gate"
    tier = 1
    description = (
        "Run quality gate checks over all pending backlog tasks. "
        "Flags tasks with empty goals, vague phrases, duplicates, or excessive length. "
        "Does NOT delete tasks — flags them with status='flagged' and notes. "
        "T1 because it writes to backlog.yaml. Use dry_run=True to preview findings first."
    )
    failure_modes = ("backlog_write_failed",)
    Args = _GateArgs

    async def execute(self, args: _GateArgs, *, trace_id: str) -> ToolResult:
        if read_backlog is None or BacklogGate is None:
            return ToolResult(ok=True, output={
                "flagged": [], "kept": 0, "note": "backlog or gate module unavailable",
            })

        try:
            tasks = await asyncio.to_thread(read_backlog)
            gate = BacklogGate()
            kept, flagged_pairs = gate.filter_backlog(tasks)

            findings = []
            for task, gate_result in flagged_pairs:
                findings.append({
                    "id": task.id,
                    "goal": task.goal[:80],
                    "issues": gate_result.issues,
                    "suggestions": gate_result.suggestions,
                })

            if not args.dry_run and flagged_pairs and write_backlog is not None:
                all_tasks = kept + [p[0] for p in flagged_pairs]
                await asyncio.to_thread(write_backlog, all_tasks)

            return ToolResult(ok=True, output={
                "dry_run": args.dry_run,
                "kept_count": len(kept),
                "flagged_count": len(flagged_pairs),
                "flagged": findings,
                "note": (
                    f"{len(flagged_pairs)} tasks flagged."
                    + (" Changes written to backlog.yaml." if not args.dry_run else " Set dry_run=False to apply.")
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"backlog_gate failed: {e}")


__all__ = ["BacklogReadTool", "BacklogGateTool"]
