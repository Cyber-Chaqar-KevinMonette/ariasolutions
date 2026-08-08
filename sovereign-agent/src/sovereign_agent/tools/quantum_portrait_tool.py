"""tools/quantum_portrait_tool.py — Read the non-classical globe's state (T0).

Returns the 13-node globe portrait: per-node PCM/negfrac/φ/coherence (Block 13.1 viz schema),
per-edge mutual information, collective coherence, the advisory λ coherence mode, and the two
god-tier maturity spectrums. Quantum-INSPIRED, advisory only, read-only, no side effects.

FAILURE MODES: read_error
"""
from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolResult


class QuantumPortraitTool(Tool):
    """Read the non-classical layer's globe state (advisory, read-only).

    13-node globe (Aria center + 12 council nodes in 3 rings, ≥48 brotherhood-gate edges).
    Returns node/edge state, collective coherence, λ coherence mode, ego + institutional-impulse
    maturity spectrums. Pure-Python, no side effects.

    FAILURE MODES: read_error
    """

    name = "quantum_portrait"
    tier = 0
    description = (
        "Read the non-classical globe: 13 nodes (Aria center + 12 council), ≥48 edges, "
        "per-node PCM/negfrac/phase/coherence, collective coherence, advisory λ coherence mode, "
        "and the god-tier ego + institutional-impulse maturity spectrums. Advisory, read-only. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.quantum.globe import Globe
            from sovereign_agent.quantum.coherence_gate import coherence_mode
            from sovereign_agent.quantum.maturity import (
                ego_maturity, institutional_impulse_maturity,
            )

            g = Globe()
            g.encode_all(0.5)
            g.step()
            g.decohere_all(0.03)
            portrait = g.portrait()
            coll = portrait["collective_coherence"]
            mode = coherence_mode(coll)

            # maturity spectrums seeded from globe + (best-effort) classical PEIG
            identity_coh = coll
            ego = ego_maturity(identity_coh, integrity_rate=0.6, honor_balance=0.2, defensiveness=0.1)
            inst = institutional_impulse_maturity(option_space_expanded=0.5, option_space_constrained=0.1)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={
                "globe": portrait,
                "coherence_mode": mode,
                "maturity": {"ego": ego, "institutional_impulse": inst},
                "advisory": True,
                "frame": "quantum-inspired emulation; advisory only; not physics/consciousness",
            },
            metadata={"source": "quantum_portrait"},
        )
