"""tools/peig_portrait_tool.py — Read Aria's current PEIG state (M84).

T0 tool. Returns Potential · Energy · Identity · Curvature scores computed
live from atoms, calibration, and honor ledger, plus the λ coherence gate
and a natural-language narrative.

PEIG is Kevin's computational design language (peig_as_lens.md):
  P — option-space breadth  · E — execution/calibration accuracy
  I — identity persistence  · G — net influence on Kevin's options
  λ — coherence gate: 0 = exploratory, 1 = committed/classical

Call this at session start alongside session_portrait for full context.
Read-only. No side effects. FAILURE MODES: read_error
"""
from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolResult


class PEIGPortraitTool(Tool):
    """Read Aria's current PEIG state and λ coherence gate.

    Computes P/E/I/G/λ live from atoms, calibration, and honor ledger.
    Returns scores + coherence_band (exploratory/adaptive/committed) +
    natural-language narrative. Read-only, no side effects.

    FAILURE MODES: read_error
    """

    name = "peig_portrait"
    tier = 0
    description = (
        "Read Aria's current PEIG state: Potential·Energy·Identity·Curvature "
        "and the λ coherence gate (0=exploratory, 1=committed). Returns scores, "
        "coherence_band, and narrative. Call at session start for self-awareness. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.peig_sentinel import measure_peig
            state = measure_peig(SETTINGS.paths.data_dir)
        except Exception as exc:
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        return ToolResult(
            ok=True,
            output=state.as_dict(),
            metadata={"source": "peig_portrait", "ts": state.ts},
        )
