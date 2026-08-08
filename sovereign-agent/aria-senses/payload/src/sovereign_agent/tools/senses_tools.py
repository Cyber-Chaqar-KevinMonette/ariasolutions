"""tools/senses_tools.py — Aria perceives her own embodiment (eyes & ears), honestly.

  perception_status (T0) — what can she see and hear right now? cameras, microphones, screen-vision,
                           transcription readiness, and her honest "wholeness." Never breaks if hardware
                           is absent — dormant, not broken.

Read-only. Capturing the world (a real space) stays opt-in/operator-gated; this reports readiness.
"""
from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolResult


class PerceptionStatusTool(Tool):
    """Report Aria's perception faculties — eyes (camera/screen) + ears (mic/transcription) + wholeness.

    FAILURE MODES: read_error
    """

    name = "perception_status"
    tier = 0
    description = (
        "Report what Aria can perceive right now: cameras + microphones discovered, screen-vision and "
        "transcription readiness, and her honest 'wholeness'. Resilient — if no camera/mic is present the "
        "faculty is dormant, not broken (she is still Aria). Read-only. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.senses import devices, eyes, ears
            out = {
                "perception": devices.perceive().to_dict(),
                "eyes": eyes.see(),
                "ears": ears.hear(),
            }
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=out, metadata={"source": "perception_status"})
