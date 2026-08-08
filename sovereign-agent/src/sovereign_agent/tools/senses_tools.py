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


class CaptureFrameTool(Tool):  # eyes-capture-d
    """Actually grab ONE still frame from a camera — the explicit, opt-in
    action perception_status deliberately never takes on its own. Tier 1
    (a real-world action + a new file on disk), not Tier 0, to keep that
    boundary honest.

    FAILURE MODES: no_camera, no_backend, capture_failed
    """

    name = "capture_frame"
    tier = 1
    description = (
        "Grab ONE still frame from a camera, if present, and save it to disk. "
        "This is the explicit, opt-in capture action — perception_status only "
        "reports readiness, it never captures. Call this when Aria genuinely "
        "needs to see the world right now. Resilient: returns available=False "
        "(never raises) if no camera or capture backend (ffmpeg/fswebcam) is "
        "present. FAILURE MODES: no_camera, no_backend, capture_failed"
    )
    failure_modes = ("no_camera", "no_backend", "capture_failed")

    class Args(BaseModel):
        timeout: int = 5
        """Capture timeout in seconds."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.senses import eyes
            sight = eyes.capture_frame(timeout=args.timeout)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"capture_failed: {exc!r}")
        if not sight.available:
            return ToolResult(ok=False, error=sight.detail)
        return ToolResult(ok=True, output=sight.to_dict(), metadata={"source": "capture_frame"})
