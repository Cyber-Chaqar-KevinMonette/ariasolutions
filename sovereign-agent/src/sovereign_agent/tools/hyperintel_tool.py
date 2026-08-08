"""hyperintel_tool.py — the HyperIntel research faculty as an agent tool.

Wraps hyperintel.engine.run(): a bounded QUESTION -> SCAN -> CROSS -> AUDIT ->
DISTILL pass over caller-supplied source files. Tier 1, propose-only — it never
acts, only produces a distilled markdown report.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from sovereign_agent.hyperintel.engine import run
from sovereign_agent.tools.base import Tool, ToolResult


class _HyperIntelArgs(BaseModel):
    question: str = Field(max_length=500, description="The research question being investigated.")
    source_paths: list[str] = Field(
        default_factory=list,
        description="File paths to read as evidence. Bounded by max_sources — extra paths beyond "
                    "the cap are ignored, never silently expanded to search elsewhere.",
    )
    max_sources: int = Field(
        default=8, ge=1, le=32,
        description="Maximum number of source files to read. Hard cap — never exceeded.",
    )


class HyperIntelTool(Tool[_HyperIntelArgs]):
    name = "hyperintel_research"
    tier = 1
    description = (
        "Run a bounded research pass (Scout/Auditor/Synthesist postures: SCAN -> CROSS-VALIDATE -> "
        "AUDIT -> DISTILL) over a fixed list of source files you provide. Only claims corroborated "
        "by 2+ independent sources are treated as trusted; single-source claims are flagged as "
        "hypotheses. Never fetches new sources on its own — propose-only, produces a markdown report."
    )
    failure_modes = ("source_unreadable", "no_sources_provided", "empty_question")
    Args = _HyperIntelArgs

    async def execute(self, args: _HyperIntelArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        if not args.question.strip():
            return ToolResult(ok=False, error="question must not be empty")
        try:
            report = run(args.question, args.source_paths, max_sources=args.max_sources)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"hyperintel run failed: {exc!r}")
        return ToolResult(
            ok=True,
            output=report.to_markdown(),
            metadata={
                "sources_scanned": len(report.sources_scanned),
                "convergent_claims": len(report.convergent_claims),
                "single_source_claims": len(report.single_source_claims),
                "risks": len(report.risks),
            },
        )
