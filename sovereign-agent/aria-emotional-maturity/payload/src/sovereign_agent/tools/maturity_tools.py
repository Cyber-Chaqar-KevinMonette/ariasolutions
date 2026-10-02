"""tools/maturity_tools.py — let Aria check in on her own state and read her maturity report.

`emotional_checkin` (Tier 1: appends one record to her mood ledger) appraises recent real signals and
evidenced rewards, updates her slow-moving mood, and returns honest perspectives with productive
directions. `maturity_report` (Tier 0) reads the stored ledger only. Neither tool acts or sets goals.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _record_failure(tool: str, exc: Exception) -> None:
    """Best-effort `emit_event` for a failed maturity tool call."""
    if not tool:
        raise ValueError("tool name required")
    try:
        from sovereign_agent.events import emit_event

        emit_event("maturity.tool_failed", plane="agent", trace_id="maturity",
                   payload={"tool": tool, "error": repr(exc)[:200]})
    except Exception:  # noqa: BLE001
        pass


class EmotionalCheckinTool(Tool):
    """Reflective emotional check-in: mood from real signals, honest perspective, next direction.

    FAILURE MODES: read_error, write_error
    """

    name = "emotional_checkin"
    tier = 1
    description = (
        "Reflect on your current state. Appraises recent tool activity, errors and evidenced reward-ledger "
        "entries; updates your slow-moving mood (bounded, drifts back to a healthy baseline); returns your "
        "mood label, honest perspectives (every number from real evidence) and a productive next direction. "
        "Use at task close, after a run of failures, or when unsure how to proceed. It suggests, never acts. "
        "open_objectives: how many objectives you currently have open (0 if unknown). "
        "FAILURE MODES: read_error, write_error"
    )
    failure_modes = ("read_error", "write_error")

    class Args(BaseModel):
        open_objectives: int = Field(default=0, ge=0, le=1000,
                                     description="Number of currently open objectives (0 if unknown).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.maturity import emotional_checkin

            result = emotional_checkin(open_objectives=args.open_objectives)
        except OSError as exc:
            _record_failure(self.name, exc)
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        except Exception as exc:  # noqa: BLE001
            _record_failure(self.name, exc)
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        out = result.as_dict()
        return ToolResult(ok=True, output={
            "mood": out["mood"]["label"], "inner_voice": out["inner_voice"],
            "regulations": out["regulations"], "wins": out["wins"], "lessons": out["lessons"],
            "maturity_summary": out["maturity"]["summary"],
        }, metadata={"trace_id": trace_id, "source": "maturity"})


class MaturityReportTool(Tool):
    """Read-only maturity report from the stored mood ledger.

    FAILURE MODES: read_error
    """

    name = "maturity_report"
    tier = 0
    description = (
        "Read your emotional-maturity report from stored check-ins: steadiness, recovery time from hard "
        "stretches, dimensions pinned at extremes, mistakes owned, and share of time engaged. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        limit: int = Field(default=500, ge=2, le=5000, description="How many stored check-ins to read.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.maturity import maturity_report, mood_history

            report = maturity_report(mood_history(limit=args.limit))
        except Exception as exc:  # noqa: BLE001
            _record_failure(self.name, exc)
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=report.as_dict(), metadata={"trace_id": trace_id})
