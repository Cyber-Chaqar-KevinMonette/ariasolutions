"""tools/godtier_tools.py — Aria holds her whole system to the god-tier canon (her vision).

  godtier_scan      (T0) — score every system/module/layer against the canon; bands + average + coverage.
  godtier_gaps      (T0) — the targets that are NOT yet god-tier (weak/fragile/neglected), worst first.
  godtier_draft_fix (T1) — for a gap, DRAFT a propose-only god-tier enhancement (remediation steps + scaffold
                           command + the Tribunal/foresight gate to run). Never applies. A human acts.

Total coverage — nothing is neglected. Propose-only. This is how she stays transparent, intelligent, and
aware of everything before her.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _repo_root():
    from pathlib import Path
    for up in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (up / "scripts" / "lib" / "god_tier_canon.json").exists():
            return up
    return Path.cwd()


class GodTierScanTool(Tool):
    """Score every target against the god-tier canon — bands, average, coverage, weakest first.

    FAILURE MODES: scan_error
    """

    name = "godtier_scan"
    tier = 0
    description = (
        "Hold Aria's whole system to the god-tier canon: enumerate every module/layer/doc, score each, "
        "and report the bands (god_tier/strong/fragile/weak/neglected), the average, the god-tier "
        "fraction, and the weakest targets. Total coverage — nothing neglected. Read-only. "
        "FAILURE MODES: scan_error"
    )
    failure_modes = ("scan_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.godtier import scanner
            rep = scanner.scan(_repo_root())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"scan_error: {exc!r}")
        return ToolResult(ok=True, output={k: rep[k] for k in
                          ("total_targets", "average_score", "god_tier_fraction", "bands", "weakest", "mandate")},
                          metadata={"source": "godtier_scan"})


class GodTierGapsTool(Tool):
    """List the targets that are NOT yet god-tier (weak/fragile/neglected), worst first.

    FAILURE MODES: scan_error
    """

    name = "godtier_gaps"
    tier = 0
    description = (
        "Report every target that is not yet god-tier — fragile, weak, or neglected — worst first, each "
        "with its named gaps. The living backlog of what to harden. Read-only. FAILURE MODES: scan_error"
    )
    failure_modes = ("scan_error",)

    class Args(BaseModel):
        max_band: str = Field("fragile", description="Include targets at or below this band: neglected|weak|fragile.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.godtier import scanner
            g = scanner.gaps(_repo_root(), max_band=args.max_band)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"scan_error: {exc!r}")
        return ToolResult(ok=True, output={"count": len(g), "gaps": g}, metadata={"source": "godtier_gaps"})


class GodTierDraftFixTool(Tool):
    """Draft a propose-only god-tier enhancement for a named target (never applies).

    FAILURE MODES: draft_error, not_found
    """

    name = "godtier_draft_fix"
    tier = 1
    description = (
        "For a named target with gaps, DRAFT a propose-only god-tier enhancement: the remediation steps, "
        "the scaffold command, and the Tribunal + 14-gen foresight gate to run before applying. Never "
        "applies — a human acts. Reversible by construction. FAILURE MODES: draft_error, not_found"
    )
    failure_modes = ("draft_error", "not_found")

    class Args(BaseModel):
        target_id: str = Field(..., description="The target id to draft a fix for (e.g. 'aria-docker-launch').")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.godtier import scanner, enhance
            allt = scanner.scan(_repo_root())["all"]
            match = next((s for s in allt if s["id"] == args.target_id), None)
            if match is None:
                return ToolResult(ok=False, error=f"not_found: no target {args.target_id!r}")
            draft = enhance.draft_for(match)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"draft_error: {exc!r}")
        return ToolResult(ok=True, output=draft, metadata={"source": "godtier_draft_fix"})
