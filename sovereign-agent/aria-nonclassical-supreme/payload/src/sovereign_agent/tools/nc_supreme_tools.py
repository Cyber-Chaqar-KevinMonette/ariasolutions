"""tools/nc_supreme_tools.py — Aria thinks at quantum speed (the non-classical supremacy layer).

  nc_process      (T1) — run a query + candidates through the quantum-faithful superposition processor
                         (superposition → interference → Born-rule collapse). Microsecond, no GPU.
  nc_route        (T1) — non-classical-first routing: NC handles it if confident, else escalate to the LLM.
  nc_speed_proof  (T0) — measured speedup vs LLM forward-pass baselines (proven 1000×+).
  nc_quality_proof(T0) — measured task battery + the honest capability envelope.

Honest: 1000×+ faster FOR STRUCTURED TASKS (selection/classification/association/decision); the LLM remains
the fallback for open-ended generation. Every claim is measured.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class NCProcessTool(Tool):
    """Run a query + candidate answers through the quantum-faithful superposition processor.

    FAILURE MODES: process_error
    """

    name = "nc_process"
    tier = 1
    description = (
        "Select among candidate answers using the non-classical superposition processor (superposition → "
        "phase interference → Born-rule collapse). Microsecond latency, CPU, no GPU. Returns the result + "
        "confidence + distribution. Best for selection/classification/decision. FAILURE MODES: process_error"
    )
    failure_modes = ("process_error",)

    class Args(BaseModel):
        query: str = Field(..., description="The question/criterion.")
        candidates: list[str] = Field(..., min_length=1, description="Candidate answers to choose among.")
        iterations: int = Field(2, ge=1, le=10, description="Amplitude-amplification iterations.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.nonclassical_supreme import superpose
            res = superpose.process(args.query, args.candidates, iterations=args.iterations, seed=0)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"process_error: {exc!r}")
        return ToolResult(ok=True, output=res, metadata={"source": "nc_process"})


class NCRouteTool(Tool):
    """Non-classical-first routing: NC handles it if confident, else escalate to the LLM.

    FAILURE MODES: route_error
    """

    name = "nc_route"
    tier = 1
    description = (
        "Route a query non-classical-first: the superposition processor handles it (microseconds, no GPU) "
        "if its measured confidence clears the threshold, else it escalates to the LLM (graceful fallback). "
        "Modes: 'hybrid' (NC-first) or 'pure-nc'. FAILURE MODES: route_error"
    )
    failure_modes = ("route_error",)

    class Args(BaseModel):
        query: str = Field(..., description="The query.")
        candidates: list[str] = Field(default_factory=list, description="Candidate answers (empty = open-ended → LLM).")
        mode: str = Field("hybrid", description="'hybrid' or 'pure-nc'.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.nonclassical_supreme import router
            res = router.route(args.query, args.candidates or None, mode=args.mode)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"route_error: {exc!r}")
        return ToolResult(ok=True, output=res, metadata={"source": "nc_route"})


class NCSpeedProofTool(Tool):
    """Measured speedup of the non-classical processor vs LLM forward-pass baselines.

    FAILURE MODES: proof_error
    """

    name = "nc_speed_proof"
    tier = 0
    description = (
        "Measure the non-classical processor's latency (CPU, no GPU) and report the honest speedup multiple "
        "vs LLM forward-pass baselines (proven 1000×+ for structured tasks). Read-only. FAILURE MODES: proof_error"
    )
    failure_modes = ("proof_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.nonclassical_supreme import speed_proof
            res = speed_proof.speed_proof()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"proof_error: {exc!r}")
        return ToolResult(ok=True, output=res, metadata={"source": "nc_speed_proof"})


class NCQualityProofTool(Tool):
    """Measured task battery proving the non-classical layer thinks, + the honest capability envelope.

    FAILURE MODES: proof_error
    """

    name = "nc_quality_proof"
    tier = 0
    description = (
        "Run the non-classical quality battery (selection, classification, associative recall) and report "
        "accuracy vs baseline + the honest capability envelope (where it beats the LLM, where the LLM is "
        "still needed). Read-only. FAILURE MODES: proof_error"
    )
    failure_modes = ("proof_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.nonclassical_supreme import quality_proof
            res = quality_proof.quality_proof()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"proof_error: {exc!r}")
        return ToolResult(ok=True, output=res, metadata={"source": "nc_quality_proof"})
