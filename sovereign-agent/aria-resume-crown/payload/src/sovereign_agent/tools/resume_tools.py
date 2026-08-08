"""
tools/resume_tools.py — Deep Resume / Pre-Action Checkpoints (M42).

  session_resume_audit()              T0 — pending checkpoints from any session
  read_checkpoints(session_id, ...)   T0 — surface pending pre-action checkpoints
  abandon_checkpoint(id, reason)      T1 — mark deliberately abandoned (reviewed)
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level import for testability (allows patch("sovereign_agent.tools.resume_tools.get_checkpoint_store"))
try:
    from sovereign_agent.checkpoint import get_checkpoint_store
except ImportError:
    get_checkpoint_store = None  # type: ignore[assignment]


# ── session_resume_audit ──────────────────────────────────────────────────────


class _AuditArgs(BaseModel):
    pass


class SessionResumeAuditTool(Tool[_AuditArgs]):
    name = "session_resume_audit"
    tier = 0
    description = (
        "Check for any pending pre-action checkpoints from previous sessions. "
        "Call at session start, after aria_status() and vessel_comfort(). "
        "If has_incomplete_actions=True: STOP and report to Kevin before doing new work. "
        "'I have N incomplete T2+ actions from last session. Should I re-run them?' "
        "Pending checkpoints are uncertainty — never silently ignore them."
    )
    failure_modes = ("checkpoint_db_unavailable",)
    Args = _AuditArgs

    async def execute(self, args: _AuditArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            store = get_checkpoint_store()
            pending = await asyncio.to_thread(store.all_pending, 10)

            actions = [c.as_dict() for c in pending]
            return ToolResult(ok=True, output={
                "has_incomplete_actions": len(pending) > 0,
                "count": len(pending),
                "actions": actions,
                "message": (
                    f"ATTENTION: {len(pending)} incomplete T2+ action(s) from previous sessions. "
                    "Report to Kevin before doing new work."
                    if pending
                    else "No incomplete actions. Session start is clean."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"session_resume_audit failed: {e}")


# ── read_checkpoints ──────────────────────────────────────────────────────────


class _ReadArgs(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to filter by. Omit to see all pending.",
    )
    status: str = Field(
        default="pending",
        description="Filter by status: 'pending', 'resolved', or 'abandoned'.",
    )
    limit: int = Field(default=10, ge=1, le=50)


class ReadCheckpointsTool(Tool[_ReadArgs]):
    name = "read_checkpoints"
    tier = 0
    description = (
        "Read pre-action checkpoints. Default: pending checkpoints (incomplete actions). "
        "Useful for auditing what T2+ actions were attempted and their outcomes. "
        "Every T2+ action you take is checkpointed — nothing is lost, everything auditable."
    )
    failure_modes = ("checkpoint_db_unavailable",)
    Args = _ReadArgs

    async def execute(self, args: _ReadArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            store = get_checkpoint_store()

            if args.session_id:
                pending = await asyncio.to_thread(store.pending_for_session, args.session_id)
            else:
                pending = await asyncio.to_thread(store.all_pending, args.limit)

            if args.status != "pending":
                # For non-pending queries, just return empty (resolved/abandoned are filtered out of query)
                return ToolResult(ok=True, output={
                    "checkpoints": [],
                    "count": 0,
                    "note": f"Resolved/abandoned checkpoints are archived. Use status='pending' for active issues.",
                })

            return ToolResult(ok=True, output={
                "checkpoints": [c.as_dict() for c in pending[:args.limit]],
                "count": len(pending),
                "status_filter": args.status,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_checkpoints failed: {e}")


# ── abandon_checkpoint ────────────────────────────────────────────────────────


class _AbandonArgs(BaseModel):
    checkpoint_id: str = Field(description="ID of the checkpoint to abandon.")
    reason: str = Field(description="Why this checkpoint is being abandoned (not re-running).")


class AbandonCheckpointTool(Tool[_AbandonArgs]):
    name = "abandon_checkpoint"
    tier = 1
    description = (
        "Mark a pending checkpoint as abandoned — the action has been reviewed "
        "and will not be re-run. Requires an explicit reason. "
        "Only abandon when Kevin has confirmed it's safe to skip. "
        "Abandoned checkpoints are preserved for audit; they are never deleted."
    )
    failure_modes = ("checkpoint_not_found", "atom_update_failed")
    Args = _AbandonArgs

    async def execute(self, args: _AbandonArgs, *, trace_id: str) -> ToolResult:
        try:
            store = get_checkpoint_store()
            await asyncio.to_thread(store.abandon, args.checkpoint_id, args.reason)
            return ToolResult(ok=True, output={
                "checkpoint_id": args.checkpoint_id,
                "status": "abandoned",
                "reason": args.reason,
                "message": "Checkpoint marked abandoned. Action will not be re-run.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"abandon_checkpoint failed: {e}")


__all__ = ["SessionResumeAuditTool", "ReadCheckpointsTool", "AbandonCheckpointTool"]
