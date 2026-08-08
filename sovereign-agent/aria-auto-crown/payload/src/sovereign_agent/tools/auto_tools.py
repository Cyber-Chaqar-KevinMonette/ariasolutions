"""tools/auto_tools.py — Timed autonomous operation tools (M43).

  auto_status()                              T0 — current auto session info
  start_auto(duration_hours, reason)         T2 — start timed auto session
  stop_auto(reason)                          T1 — graceful early stop
  extend_auto(additional_hours)              T3 — extend current session
  set_auto_trust_tier(tier)                  T3 — set operator trust tier
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level import for testability
try:
    from sovereign_agent.auto_crown import get_auto_crown_store
except ImportError:
    get_auto_crown_store = None  # type: ignore[assignment]


# ── auto_status ───────────────────────────────────────────────────────────────


class _StatusArgs(BaseModel):
    pass


class AutoStatusTool(Tool[_StatusArgs]):
    name = "auto_status"
    tier = 0
    description = (
        "Check the current autonomous operation session. "
        "Returns active session details, remaining time, work done, and trust tier. "
        "Call to know how much autonomous time remains before the timer expires."
    )
    failure_modes = ("auto_crown_unavailable",)
    Args = _StatusArgs

    async def execute(self, args: _StatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            store = get_auto_crown_store()
            session = await asyncio.to_thread(store.status)
            max_tier = await asyncio.to_thread(store.get_max_trust_tier)
            if session is None:
                return ToolResult(ok=True, output={
                    "active": False,
                    "message": "No active auto session.",
                    "max_trust_tier": max_tier,
                })
            remaining_min = session.remaining_minutes()
            return ToolResult(ok=True, output={
                "active": session.status == "active",
                "session_id": session.session_id,
                "started_at": session.started_at,
                "duration_hours": session.duration_hours,
                "trust_tier": session.trust_tier,
                "reason": session.reason,
                "status": session.status,
                "remaining_minutes": round(remaining_min, 1),
                "remaining_label": f"{int(remaining_min)}m" if remaining_min > 0 else "expired",
                "work_done_summary": session.work_done_summary,
                "is_expired": session.status == "expired" or remaining_min <= 0,
                "max_trust_tier": max_tier,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"auto_status failed: {e}")


# ── start_auto ────────────────────────────────────────────────────────────────


class _StartArgs(BaseModel):
    duration_hours: float = Field(
        ge=0.1,
        le=8.0,
        description="How long to run autonomously (hours). Max governed by trust tier.",
    )
    reason: str = Field(
        max_length=500,
        description="What will be worked on during this auto session.",
    )


class StartAutoTool(Tool[_StartArgs]):
    name = "start_auto"
    tier = 2
    description = (
        "Start a timed autonomous operation session. Aria works until the timer expires. "
        "Trust tier governs max duration: tier 1=1hr, 2=2hr, 3=4hr, 4=8hr. "
        "Kevin must confirm (T2). Tier ceiling stays T1 throughout — safety unchanged. "
        "Timer is stored in auto_crown.json and checked at each loop iteration."
    )
    failure_modes = ("trust_tier_exceeded", "duration_too_long", "auto_crown_unavailable")
    Args = _StartArgs

    async def execute(self, args: _StartArgs, *, trace_id: str) -> ToolResult:
        try:
            store = get_auto_crown_store()
            max_tier = await asyncio.to_thread(store.get_max_trust_tier)
            max_hours = {1: 1.0, 2: 2.0, 3: 4.0, 4: 8.0}.get(max_tier, 1.0)

            session = await asyncio.to_thread(
                store.start,
                args.duration_hours,
                max_tier,
                args.reason,
                trace_id,
            )
            return ToolResult(ok=True, output={
                "session_id": session.session_id,
                "started_at": session.started_at,
                "duration_hours": session.duration_hours,
                "trust_tier": session.trust_tier,
                "reason": session.reason,
                "remaining_minutes": round(session.remaining_minutes(), 1),
                "message": (
                    f"Auto session started. Running for {args.duration_hours}h "
                    f"(trust tier {session.trust_tier}, max {max_hours}h). "
                    "Timer is live. I will stop gracefully when it expires."
                ),
            })
        except ValueError as e:
            return ToolResult(ok=False, error=str(e))
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"start_auto failed: {e}")


# ── stop_auto ─────────────────────────────────────────────────────────────────


class _StopArgs(BaseModel):
    reason: str = Field(max_length=500, description="Why stopping early.")
    work_done_summary: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="What was accomplished before stopping.",
    )


class StopAutoTool(Tool[_StopArgs]):
    name = "stop_auto"
    tier = 1
    description = (
        "Stop the current autonomous session early. Records a work summary and "
        "marks the session cancelled. Timer is cleared immediately."
    )
    failure_modes = ("no_active_session", "auto_crown_unavailable")
    Args = _StopArgs

    async def execute(self, args: _StopArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            store = get_auto_crown_store()
            session = await asyncio.to_thread(store.status)
            if session is None or session.status != "active":
                return ToolResult(ok=False, error="No active auto session to stop.")
            summary = args.work_done_summary or args.reason
            await asyncio.to_thread(store.cancel, summary)
            return ToolResult(ok=True, output={
                "session_id": session.session_id,
                "status": "cancelled",
                "reason": args.reason,
                "work_done_summary": summary,
                "message": "Auto session cancelled. Timer cleared.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"stop_auto failed: {e}")


# ── extend_auto ───────────────────────────────────────────────────────────────


class _ExtendArgs(BaseModel):
    additional_hours: float = Field(
        ge=0.1,
        le=4.0,
        description="Additional hours to add to the current session.",
    )


class ExtendAutoTool(Tool[_ExtendArgs]):
    name = "extend_auto"
    tier = 3
    requires_approval = True
    description = (
        "Extend the current auto session by additional hours. T3 — requires operator approval. "
        "Cannot extend an expired or cancelled session."
    )
    failure_modes = (
        "no_active_session",
        "auto_crown_unavailable",
        "approval_required",
    )
    Args = _ExtendArgs

    async def execute(self, args: _ExtendArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            store = get_auto_crown_store()
            session = await asyncio.to_thread(store.status)
            if session is None or session.status != "active":
                return ToolResult(ok=False, error="No active auto session to extend.")

            session.expires_at += args.additional_hours * 3600
            session.duration_hours += args.additional_hours
            await asyncio.to_thread(store._write, session)

            return ToolResult(ok=True, output={
                "session_id": session.session_id,
                "extended_by_hours": args.additional_hours,
                "new_duration_hours": session.duration_hours,
                "remaining_minutes": round(session.remaining_minutes(), 1),
                "message": f"Session extended by {args.additional_hours}h.",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"extend_auto failed: {e}")


# ── set_auto_trust_tier ───────────────────────────────────────────────────────


class _SetTierArgs(BaseModel):
    tier: int = Field(
        ge=1,
        le=4,
        description=(
            "Trust tier to set (1=1hr max, 2=2hr, 3=4hr, 4=8hr). "
            "T3 — operator approval required."
        ),
    )


class SetAutoTrustTierTool(Tool[_SetTierArgs]):
    name = "set_auto_trust_tier"
    tier = 3
    requires_approval = True
    description = (
        "Set the maximum trust tier for autonomous sessions. T3 — requires operator approval. "
        "Tier 1: max 1hr (default). Tier 2: max 2hr. Tier 3: max 4hr. Tier 4: max 8hr. "
        "Raise only after demonstrated reliability."
    )
    failure_modes = ("invalid_tier", "auto_crown_unavailable", "approval_required")
    Args = _SetTierArgs

    async def execute(self, args: _SetTierArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            store = get_auto_crown_store()
            await asyncio.to_thread(store.set_trust_tier, args.tier)
            max_hours = {1: 1.0, 2: 2.0, 3: 4.0, 4: 8.0}[args.tier]
            return ToolResult(ok=True, output={
                "trust_tier": args.tier,
                "max_hours": max_hours,
                "message": (
                    f"Trust tier set to {args.tier} "
                    f"(max {max_hours}h per auto session)."
                ),
            })
        except ValueError as e:
            return ToolResult(ok=False, error=str(e))
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"set_auto_trust_tier failed: {e}")


__all__ = [
    "AutoStatusTool",
    "StartAutoTool",
    "StopAutoTool",
    "ExtendAutoTool",
    "SetAutoTrustTierTool",
]
