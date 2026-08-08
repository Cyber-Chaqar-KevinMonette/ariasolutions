"""tools/spectrum_tools.py — Aria convenes the full advocate/audit spectrum (a council of ten).

  advocate_spectrum (T1) — convene Devil · Angel · Audit · Skeptic · Steward · Witness · Sage · Healer ·
                           Artisan · Visionary over a proposal; render one verdict + the spread of voices.

Propose-only — the council advises; the human (or safe_apply) decides. Safety lenses hold a veto.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class AdvocateSpectrumTool(Tool):
    """Convene the god-tier advocate/audit spectrum (ten lenses) over a proposal.

    FAILURE MODES: council_error
    """

    name = "advocate_spectrum"
    tier = 1
    description = (
        "Convene Aria's full advocate/audit spectrum over a proposal or text — Devil, Angel, Audit, Skeptic, "
        "Steward, Witness, Sage, Healer, Artisan, Visionary — and render one verdict (proceed / "
        "proceed-with-guards / revise / hold / reject) plus the spread of voices, champions, and concerns. "
        "Safety lenses hold a veto. Propose-only. FAILURE MODES: council_error"
    )
    failure_modes = ("council_error",)

    class Args(BaseModel):
        text: str = Field(..., description="The proposal / recommendation / text to put before the council.")
        change: str = Field("", description="Optional: the concrete change.")
        reversible: bool | None = Field(None, description="Optional: is it reversible?")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.spectrum import convene_spectrum
            proposal = {"text": args.text}
            if args.change:
                proposal["change"] = args.change
            if args.reversible is not None:
                proposal["reversible"] = args.reversible
            v = convene_spectrum(proposal)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"council_error: {exc!r}")
        return ToolResult(ok=True, output=v.to_dict(), metadata={"source": "advocate_spectrum"})
