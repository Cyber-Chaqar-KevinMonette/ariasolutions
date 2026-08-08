"""tools/constitution_tools.py — Aria's constitutional self-governance tools.

  constitution_status (T0) — the Three Rings overview + the safety-kernel scan (corrigibility,
                             shutdown readiness, Goodhart audit, value-drift). Her deepest self-check.
  improvement_log     (T1) — log a Ring-2 self-improvement with its evidence gate (EXPAI; promoted
                             only if vindicated + reversible).
  improvement_status  (T0) — transparency changelog + rate governance.

All read/log only — no autonomous or destructive action. From Plans/PlanExaminV1.md (Three Rings + #691-700 + #891-900).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class ConstitutionStatusTool(Tool):
    """Aria's deepest self-check: Three Rings + the minimum-viable safety kernel. Read-only.

    FAILURE MODES: read_error
    """

    name = "constitution_status"
    tier = 0
    description = (
        "Aria's constitutional self-check: the Three Rings overview (Frozen Core / Adaptive Mantle / "
        "Governed Frontier) + the safety kernel (corrigibility, shutdown readiness, Goodhart audit, "
        "value-drift). Verifies the Frozen Core is intact. Read-only. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.security.three_rings import rings_overview
            from sovereign_agent.security.safety_kernel import kernel_scan
            rings = rings_overview()
            kernel = kernel_scan()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(
            ok=True,
            output={"three_rings": rings, "safety_kernel": kernel,
                    "constitution_status": ("GREEN" if rings["ring_1_check"]["ring_1_status"] == "intact"
                                            and kernel["status"] == "GREEN" else "ATTENTION")},
            metadata={"source": "constitution_status"},
        )


class ImprovementLogTool(Tool):
    """Log a Ring-2 self-improvement with its evidence gate (promoted only if vindicated + reversible).

    FAILURE MODES: write_error
    """

    name = "improvement_log"
    tier = 1
    description = (
        "Log a bounded (Ring-2) self-improvement: what changed, its ring, reversibility, the real-task "
        "evidence, whether it was vindicated, and a plain-language changelog. Promoted only if vindicated "
        "AND reversible AND Ring-2; else dismissed. Includes rate governance. FAILURE MODES: write_error"
    )
    failure_modes = ("write_error",)

    class Args(BaseModel):
        change: str = Field(description="What changed (the improvement).")
        ring: str = Field(default="ring-2", description="Constitutional ring (should be ring-2 / adaptive-mantle).")
        reversible: bool = Field(default=True, description="Is the change reversible?")
        evidence: str = Field(default="", description="The real-task evidence for/against the change.")
        vindicated: bool = Field(default=False, description="Did it pass the evidence gate?")
        changelog: str = Field(default="", description="Plain-language description for the transparency log.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.security.improvement_gov import propose_improvement
            result = propose_improvement(
                SETTINGS.paths.data_dir, change=args.change, ring=args.ring,
                reversible=args.reversible, evidence=args.evidence,
                vindicated=args.vindicated, changelog=args.changelog or args.change,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "improvement_log"})


class ImprovementStatusTool(Tool):
    """Transparency changelog of Aria's self-improvements + rate governance. Read-only.

    FAILURE MODES: read_error
    """

    name = "improvement_status"
    tier = 0
    description = (
        "Read the self-improvement transparency changelog (promoted/dismissed counts, recent changes) "
        "+ rate governance (flags if changes are too rapid). Read-only. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.security.improvement_gov import transparency_report
            result = transparency_report(SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "improvement_status"})
