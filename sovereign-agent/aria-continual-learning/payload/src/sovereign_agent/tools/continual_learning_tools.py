"""tools/continual_learning_tools.py — bounded, propose-only continual-learning surface.

  propose_retrain (T1) — check whether enough new Reflector lessons have
                          accumulated to warrant retraining Aria's own
                          from-scratch model (aria_lm), and if so, PROPOSE
                          it — never auto-execute. Training a base-weight
                          model stays Tier 3 / human-gated per
                          aria_lm_tools.py's own doctrine.

Reuses aria_lm.retrain_trigger.check_retrain_proposal — this tool is a
thin surface over it, not new logic.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class ProposeRetrainTool(Tool):
    """Check whether enough new lessons have accumulated to propose
    retraining Aria's own from-scratch model. Never trains — propose only.

    FAILURE MODES: check_error
    """

    name = "propose_retrain"
    tier = 1
    description = (
        "Check whether enough Reflector lessons have accumulated since the last training run to "
        "propose retraining Aria's own from-scratch model (aria_lm). Never trains — this only "
        "reports whether a retrain is due and, if so, the command a human would run. Training a "
        "base-weight model stays Tier 3 / human-gated. FAILURE MODES: check_error"
    )
    failure_modes = ("check_error",)

    class Args(BaseModel):
        threshold: int = Field(
            20, ge=1, le=1000,
            description="Minimum new lessons since the last retrain before proposing one.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.aria_lm.retrain_trigger import check_retrain_proposal

            proposal = check_retrain_proposal(SETTINGS.paths.data_dir, threshold=args.threshold)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"check_error: {exc!r}")

        if proposal is None:
            return ToolResult(
                ok=True,
                output={"due": False, "threshold": args.threshold},
                metadata={"source": "propose_retrain"},
            )
        return ToolResult(ok=True, output=proposal, metadata={"source": "propose_retrain"})
