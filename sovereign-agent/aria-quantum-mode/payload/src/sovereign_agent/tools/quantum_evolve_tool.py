"""tools/quantum_evolve_tool.py — Evolve the globe one ILP lineage generation (T1).

Loads the persisted globe, runs coupling steps, saves it forward — so the non-classical layer
EVOLVES across sessions (the Infinite Lineage Protocol). Returns the evolved globe portrait +
lineage generation. Advisory only; the only write is the globe's own state snapshot.

FAILURE MODES: evolve_error
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class QuantumEvolveTool(Tool):
    """Evolve the non-classical globe one lineage generation (persists state forward).

    Loads persisted globe → couples → saves. The globe carries its phases across sessions
    (ILP). Returns evolved portrait + lineage_generation. Advisory.

    FAILURE MODES: evolve_error
    """

    name = "quantum_evolve"
    tier = 1
    description = (
        "Evolve the non-classical globe one Infinite-Lineage-Protocol generation: load persisted "
        "state, run coupling steps, save forward. The globe carries its phases across sessions. "
        "Returns the evolved globe portrait + lineage_generation. Advisory. FAILURE MODES: evolve_error"
    )
    failure_modes = ("evolve_error",)

    class Args(BaseModel):
        steps: int = Field(default=3, description="Coupling sweeps (1-8).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.persist import evolve
            steps = max(1, min(8, args.steps))
            portrait = evolve(SETTINGS.paths.data_dir, steps=steps)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"evolve_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={
                "lineage_generation": portrait.get("lineage_generation"),
                "self_coherence": portrait.get("self_coherence"),
                "ascii_view": portrait.get("ascii_view"),
                "advisory": True,
            },
            metadata={"source": "quantum_evolve"},
        )
