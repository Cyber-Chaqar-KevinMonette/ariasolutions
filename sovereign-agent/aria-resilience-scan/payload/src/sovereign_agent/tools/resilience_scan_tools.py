"""tools/resilience_tools.py — Aria probes her own robustness across both layers.

  resilience_scan (T0) — run the edge-case battery over the classical + non-classical entry points and
                         report whether each degrades gracefully (or which inputs wedge it).

Read-only. God-tier resilience = nothing wedges; everything degrades to a clear value/status.
"""
from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolResult


class ResilienceScanTool(Tool):
    """Probe both layers with the edge-case battery; certify graceful degradation.

    FAILURE MODES: scan_error
    """

    name = "resilience_scan"
    tier = 0
    description = (
        "Run Aria's edge-case battery (empty / huge / malformed / unicode / timeout) over the classical and "
        "non-classical layer entry points, and report whether each degrades gracefully or which inputs wedge "
        "it. God-tier resilience = nothing wedges. Read-only. FAILURE MODES: scan_error"
    )
    failure_modes = ("scan_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.resilience_scan import layers
            rep = layers.scan_both_layers()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"scan_error: {exc!r}")
        return ToolResult(ok=True, output=rep, metadata={"source": "resilience_scan"})
