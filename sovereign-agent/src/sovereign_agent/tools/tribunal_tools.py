"""tools/tribunal_tools.py — Aria convenes her god-tier scrutiny system.

  tribunal_review (T1) — convene Devil + Angel + Audit over a proposal/text; render a verdict + synthesis.
  devils_advocate (T0) — adversary only: hunt what breaks (severity-scored findings).
  angels_advocate (T0) — advocate only: name what's worth protecting + concrete paths forward.
  tribunal_audit  (T0) — independent evidence verification (grounding + file claims + safety kernel).

All propose-only — they render verdicts/findings; the operator acts. The antidote to ungrounded
profundity: a claim that "sounds true" is held against evidence and the safety kernel.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class TribunalReviewTool(Tool):
    """Convene the full Tribunal (Devil · Angel · Audit) over a proposal and render a verdict.

    FAILURE MODES: review_error
    """

    name = "tribunal_review"
    tier = 1
    description = (
        "Convene Aria's god-tier scrutiny Tribunal over a proposal or text: the Devil hunts what breaks, "
        "the Angel names what's worth protecting, the Audit verifies claims against reality. Renders a "
        "verdict (proceed / proceed-with-guards / revise / hold / reject) + synthesis (gaps · risks · "
        "protect · paths-forward). Propose-only. FAILURE MODES: review_error"
    )
    failure_modes = ("review_error",)

    class Args(BaseModel):
        text: str = Field(..., description="The proposal, recommendation, or text to scrutinize.")
        change: str = Field("", description="Optional: the concrete change being proposed.")
        reversible: bool | None = Field(None, description="Optional: is the change reversible?")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.tribunal import convene
            proposal = {"text": args.text}
            if args.change:
                proposal["change"] = args.change
            if args.reversible is not None:
                proposal["reversible"] = args.reversible
            v = convene(proposal)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"review_error: {exc!r}")
        return ToolResult(ok=True, output=v.to_dict(), metadata={"source": "tribunal_review"})


class DevilsAdvocateTool(Tool):
    """Adversarial scrutiny only: hunt gaps, risks, failure modes, ungrounded claims, safety drift.

    FAILURE MODES: review_error
    """

    name = "devils_advocate"
    tier = 0
    description = (
        "Run the Devil's Advocate over a text/proposal: severity-scored findings (blocking / material / "
        "stewardship) across grounding, reversibility, failure modes, Goodhart, value-drift, lock-in, "
        "and DEFERRED_UNSAFE proximity. Read-only, propose-only. FAILURE MODES: review_error"
    )
    failure_modes = ("review_error",)

    class Args(BaseModel):
        text: str = Field(..., description="The text or proposal to attack.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.tribunal import devil
            rep = devil.scrutinize(args.text)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"review_error: {exc!r}")
        return ToolResult(ok=True, output=rep.to_dict(), metadata={"source": "devils_advocate"})


class AngelsAdvocateTool(Tool):
    """Advocate scrutiny: name the real value worth protecting + concrete paths forward.

    FAILURE MODES: review_error
    """

    name = "angels_advocate"
    tier = 0
    description = (
        "Run the Angel's Advocate over a text/proposal: the strongest case FOR, what must not be lost, "
        "and each critique turned into a concrete path forward. Guards against over-rejection. Read-only. "
        "FAILURE MODES: review_error"
    )
    failure_modes = ("review_error",)

    class Args(BaseModel):
        text: str = Field(..., description="The text or proposal to advocate for.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.tribunal import angel, devil
            d = devil.scrutinize(args.text)
            rep = angel.advocate(args.text, devil_report=d)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"review_error: {exc!r}")
        return ToolResult(ok=True, output=rep.to_dict(), metadata={"source": "angels_advocate"})


class TribunalAuditTool(Tool):
    """Independent evidence verification: grounding + file-existence claims + the safety kernel.

    FAILURE MODES: audit_error
    """

    name = "tribunal_audit"
    tier = 0
    description = (
        "Audit a text/proposal against reality: classify its claims (evidence-backed / hypothesis / "
        "ungrounded / mystical-fog), verify any referenced files exist, and run the safety kernel + "
        "Frozen-Core check. Returns an evidence ledger. Read-only. FAILURE MODES: audit_error"
    )
    failure_modes = ("audit_error",)

    class Args(BaseModel):
        text: str = Field("", description="The text/proposal to audit. Empty = audit the system's own safety posture.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.tribunal import audit as _audit
            text = args.text or "system self-audit: safety kernel + frozen core intact"
            ledger = _audit.audit({"text": text}, include_kernel=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"audit_error: {exc!r}")
        return ToolResult(ok=True, output=ledger.to_dict(), metadata={"source": "tribunal_audit"})
