"""tools/foresight_tools.py — Aria thinks 14 generations ahead + consults the Ultimate Questions.

  foresight_14gen  (T1) — project a decision across 14 generations: intergenerational equity, lock-in,
                          value-drift, reversibility + a verdict + far-horizon reflection.
  ultimate_question (T0) — query the 400 Ultimate Questions (by keyword / tier / number) for reflection.

Read-only / propose-only. Structured foresight, not prophecy; cosmic questions are vision, never claims.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class Foresight14GenTool(Tool):
    """Project a decision 14 generations ahead — intergenerational equity + a verdict.

    FAILURE MODES: foresight_error
    """

    name = "foresight_14gen"
    tier = 1
    description = (
        "Think 14 generations ahead about an architectural decision: score intergenerational equity, "
        "lock-in, value-drift risk, and reversibility across G+1..G+14, render a verdict (carry-forward / "
        "escalate / reject-for-the-future), and surface relevant north-star Ultimate Questions. "
        "Structured foresight, not prophecy. FAILURE MODES: foresight_error"
    )
    failure_modes = ("foresight_error",)

    class Args(BaseModel):
        decision: str = Field(..., description="The architectural decision / commitment to project.")
        reversible: bool | None = Field(None, description="Optional: is it reversible?")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.foresight import project
            d = {"text": args.decision}
            if args.reversible is not None:
                d["reversible"] = args.reversible
            f = project(d)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"foresight_error: {exc!r}")
        return ToolResult(ok=True, output=f.to_dict(), metadata={"source": "foresight_14gen"})


class UltimateQuestionTool(Tool):
    """Query the 400 Ultimate Questions (Gen-7→100 north star) for reflection.

    FAILURE MODES: read_error
    """

    name = "ultimate_question"
    tier = 0
    description = (
        "Query Aria's baked-in catalog of the 400 Ultimate Questions (Kevin's Gen-7→100 north star), by "
        "keyword / tier (actionable-now | near-term | north-star-reflection) / number. For reflection and "
        "horizon-scanning — cosmic questions are vision, never claimed as built. Read-only. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        keyword: str = Field("", description="Keyword to search (empty = browse).")
        tier: str = Field("", description="Optional tier filter: actionable-now | near-term | north-star-reflection.")
        number: int = Field(0, ge=0, le=400, description="Optional: fetch a specific question by number.")
        limit: int = Field(10, ge=1, le=50, description="Max results.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.foresight import ultimate_questions as uq
            if args.number:
                q = uq.get(args.number)
                out = {"question": q, "summary": uq.summary()}
            else:
                out = {"results": uq.search(args.keyword, tier=args.tier or None, limit=args.limit),
                       "summary": uq.summary()}
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=out, metadata={"source": "ultimate_question"})
