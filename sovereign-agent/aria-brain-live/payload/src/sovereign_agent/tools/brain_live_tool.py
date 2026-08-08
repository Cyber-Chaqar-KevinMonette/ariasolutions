"""tools/brain_live_tool.py — Bounded live-mode burst: her brain thinks continuously (safely).

  brain_live (T1) — run a BOUNDED burst of generative ticks; returns the stream of thoughts + status.
Ring-buffered and tick-capped so it can never flood the system. The threaded always-on runner lives
in quantum/brain_live.py (LiveBrain.start/stop) for cockpit use; this tool is the safe request form.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class BrainLiveTool(Tool):
    """Run a bounded burst of continuous brain thoughts (safe always-running substrate).

    FAILURE MODES: live_error
    """

    name = "brain_live"
    tier = 1
    description = (
        "Run Aria's nested brain in a BOUNDED live burst: N generative ticks (capped), ring-buffered, "
        "CPU-yielding — it can never flood the system. Returns the stream of thoughts + status. "
        "FAILURE MODES: live_error"
    )
    failure_modes = ("live_error",)

    class Args(BaseModel):
        ticks: int = Field(default=5, description="Number of bounded generative ticks (1-30).")
        length: int = Field(default=60, description="Length of each thought.")
        temp: float = Field(default=0.25, description="Temperature (0.05-1.5).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.brain_live import LiveBrain
            ticks = max(1, min(30, args.ticks))     # hard cap on burst size
            live = LiveBrain(SETTINGS.paths.data_dir, length=args.length, temp=args.temp)
            done = live.run_ticks(ticks)
            return ToolResult(
                ok=True,
                output={
                    "ticks_run": done,
                    "thoughts": live.thoughts(),
                    "status": live.status(),
                    "note": "Bounded live burst — ring-buffered + CPU-yielding; never floods the system.",
                },
                metadata={"source": "brain_live"},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"live_error: {exc!r}")
