"""tools/autonomy_tools.py — Aria's supervised autonomy: plan, propose a block, work bounded, pause, resume.

  autonomy_plan    (T1) — build/extend a living plan (the spine of a session).
  autonomy_propose (T1) — propose a session + present the human their options (she never self-starts).
  autonomy_status  (T0) — the live observation stream: what she's doing, time remaining, checkpoint.
  autonomy_pause   (T1) — pause with a resumable checkpoint (done / next).

Starting a block is a human action (Option 1 approval) — it is gated outside these tools. The bounded
blast-radius (staged drafting / verify / scrutiny only; never outward, never sealed, never apply) is
enforced in session.record_action. Observable, reversible, always-stoppable.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _data_dir():
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir


class AutonomyPlanTool(Tool):
    """Create or extend a living plan for a supervised autonomy session.

    FAILURE MODES: plan_error
    """

    name = "autonomy_plan"
    tier = 1
    description = (
        "Create or extend a living, versioned plan for a supervised autonomy session — the spine Aria "
        "works, observed. Plans grow over time even as she works. FAILURE MODES: plan_error"
    )
    failure_modes = ("plan_error",)

    class Args(BaseModel):
        title: str = Field(..., description="Plan title.")
        steps: list[str] = Field(default_factory=list, description="Initial steps.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.autonomy import plan_forge
            plan = plan_forge.new_plan(args.title, args.steps)
            plan_forge.save(plan, _data_dir())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"plan_error: {exc!r}")
        return ToolResult(ok=True, output={"plan": plan.to_dict(), "progress": plan_forge.progress(plan)},
                          metadata={"source": "autonomy_plan"})


class AutonomyProposeTool(Tool):
    """Propose a supervised autonomy session and present the human their options (she never self-starts).

    FAILURE MODES: propose_error
    """

    name = "autonomy_propose"
    tier = 1
    description = (
        "Propose a bounded autonomy session for a plan and present the human their options (approve a "
        "~90-min block / edit the plan / discuss). Shows the bounded action set and what is never allowed. "
        "Propose-only — the human approves to start. FAILURE MODES: propose_error"
    )
    failure_modes = ("propose_error",)

    class Args(BaseModel):
        plan_id: str = Field(..., description="The plan to work.")
        minutes: int = Field(90, ge=1, le=120, description="Requested block length (max 120; >120 is Tier-3).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.autonomy import session
            out = session.propose_session(args.plan_id, ttl_seconds=args.minutes * 60)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"propose_error: {exc!r}")
        return ToolResult(ok=True, output=out, metadata={"source": "autonomy_propose"})


class AutonomyStatusTool(Tool):
    """The live observation stream for a session — what she's doing, time left, checkpoint.

    FAILURE MODES: read_error, not_found
    """

    name = "autonomy_status"
    tier = 0
    description = (
        "Show a supervised autonomy session's live status: recent actions (the observation stream), time "
        "remaining in the block, status, and the resumable checkpoint. Read-only — for the human watching. "
        "FAILURE MODES: read_error, not_found"
    )
    failure_modes = ("read_error", "not_found")

    class Args(BaseModel):
        session_id: str = Field(..., description="The session id.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.autonomy import session
            s = session.load(args.session_id, _data_dir())
            if s is None:
                return ToolResult(ok=False, error=f"not_found: no session {args.session_id!r}")
            session.expire_if_due(s)
            out = {"status": s.status, "time_remaining_s": session.time_remaining(s),
                   "blocks_completed": s.blocks_completed, "checkpoint": s.checkpoint,
                   "recent_actions": session.observe(s, tail=15)}
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=out, metadata={"source": "autonomy_status"})


class AutonomyPauseTool(Tool):
    """Pause a session with a resumable checkpoint (done / next).

    FAILURE MODES: pause_error, not_found
    """

    name = "autonomy_pause"
    tier = 1
    description = (
        "Pause a supervised autonomy session, writing a resumable checkpoint (what's done, what's next) so "
        "the human can continue, re-approve another block, or enter plan mode. FAILURE MODES: pause_error, not_found"
    )
    failure_modes = ("pause_error", "not_found")

    class Args(BaseModel):
        session_id: str = Field(..., description="The session id.")
        done: str = Field(..., description="What was accomplished this block.")
        next_up: str = Field(..., description="Where to resume.")
        notes: str = Field("", description="Any notes for the human / next block.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.autonomy import session
            s = session.load(args.session_id, _data_dir())
            if s is None:
                return ToolResult(ok=False, error=f"not_found: no session {args.session_id!r}")
            session.pause(s, done=args.done, next_up=args.next_up, notes=args.notes)
            session.save(s, _data_dir())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"pause_error: {exc!r}")
        return ToolResult(ok=True, output={"status": s.status, "checkpoint": s.checkpoint},
                          metadata={"source": "autonomy_pause"})
