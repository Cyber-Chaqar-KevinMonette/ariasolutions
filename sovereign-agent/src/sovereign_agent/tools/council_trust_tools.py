"""tools/council_trust_tools.py — Council trust ledger tools (witnessing track record).

  council_record_outcome (T1) — resolve a logged consult with its real outcome
  council_calibration    (T0) — read the council's track record (accuracy + trust band)

Logging of consults happens automatically inside quantum_consult. These tools let the council's
advice be VERIFIED against reality over time — the non-classical layer earns trust by being right.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class CouncilRecordOutcomeTool(Tool):
    """Resolve a logged council consult with what actually happened (yes/no).

    Builds the council's verified track record. FAILURE MODES: not_found, invalid_outcome, write_error
    """

    name = "council_record_outcome"
    tier = 1
    description = (
        "Resolve a past council consult with its real outcome (yes/no), to build the council's "
        "verified track record. Args: consult_id, outcome. FAILURE MODES: not_found, invalid_outcome, write_error"
    )
    failure_modes = ("not_found", "invalid_outcome", "write_error")

    class Args(BaseModel):
        consult_id: str = Field(description="The consult_id from a prior quantum_consult.")
        outcome: str = Field(description="What actually happened: yes or no.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.trust import record_outcome
            r = record_outcome(SETTINGS.paths.data_dir, consult_id=args.consult_id, outcome=args.outcome)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        if not r.get("ok"):
            return ToolResult(ok=False, error=r.get("error", "not_found"))
        return ToolResult(ok=True, output=r, metadata={"source": "council_record_outcome"})


class CouncilCalibrationTool(Tool):
    """Read the council's verified track record: accuracy + trust band. Read-only.

    FAILURE MODES: read_error
    """

    name = "council_calibration"
    tier = 0
    description = (
        "Read the non-classical council's verified track record: total/resolved consults, accuracy, "
        "and trust band (unproven/promising/trusted/unreliable). The council earns higher roles only "
        "by proving accuracy at scale. Read-only. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.trust import calibration
            cal = calibration(SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=cal, metadata={"source": "council_calibration"})
