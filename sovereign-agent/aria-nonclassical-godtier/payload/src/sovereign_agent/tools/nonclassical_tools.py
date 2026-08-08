"""tools/nonclassical_tools.py — certify the non-classical layer is god-tier (robust + on-par-or-better).

  nonclassical_certify (T0) — run the robustness scan + the parity benchmark and report whether the
                              non-classical (PEIG/quantum) layer meets the god-tier bar: deterministic,
                              gracefully degrading, bounded, and on par with or better than classical.

Read-only. Honest: parity is measured, never asserted without the number. Training the brain is bounded
(a few epochs) and CPU-only.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class NonClassicalCertifyTool(Tool):
    """Certify the non-classical layer: robustness scan + parity benchmark vs classical.

    FAILURE MODES: certify_error
    """

    name = "nonclassical_certify"
    tier = 0
    description = (
        "Certify Aria's non-classical (PEIG/quantum) layer to the god-tier bar: determinism, graceful "
        "degradation, bounded learning, and a parity benchmark vs a classical baseline (on par or better). "
        "Honest — parity is measured, not claimed. Read-only. FAILURE MODES: certify_error"
    )
    failure_modes = ("certify_error",)

    class Args(BaseModel):
        epochs: int = Field(40, ge=4, le=120, description="Brain training epochs for the parity benchmark.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.nonclassical import robustness, parity
            rob = robustness.robustness_scan()
            par = parity.benchmark(epochs=args.epochs)
            certified = bool(rob.get("god_tier_robust") and par.get("on_par_or_better"))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"certify_error: {exc!r}")
        return ToolResult(ok=True, output={
            "certified_god_tier": certified,
            "robustness": {"god_tier_robust": rob.get("god_tier_robust"),
                           "determinism": rob.get("determinism", {}).get("ok"),
                           "graceful_degradation": rob.get("graceful_degradation", {}).get("ok"),
                           "bounded_learning": rob.get("bounded_learning", {}).get("ok")},
            "parity": par,
        }, metadata={"source": "nonclassical_certify"})
