"""tools/business_playbook_tools.py — read-only lookup over the curated
secular business/leadership/negotiation frameworks in business_playbook.py.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class BusinessPlaybookTool(Tool):
    """Look up curated business/leadership/negotiation/communication frameworks.

    Deterministic keyword match over a static, hand-curated corpus (not free-form LLM
    generation) — same discipline as the consumer-law and real-estate-strategy companions.
    Every entry is a secular, practical framework; source is disclosed on each result.

    FAILURE MODES: read_error
    """

    name = "business_playbook"
    tier = 0
    description = (
        "Look up curated business/leadership/communication/negotiation frameworks "
        "(e.g. negotiation, hiring, trust, forgiveness, purpose statement, team leadership). "
        "query: free-text search term. category: optional exact-match filter "
        "(purpose, discipline, leadership-commitment, communication, forgiveness, conflict, "
        "trust, leadership, excellence, engineering, strategy, hiring, negotiation, pricing). "
        "Returns matched frameworks with steps, principles, and source. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        query: str = Field(default="", description="Free-text search term, e.g. 'negotiation' or 'trust'.")
        category: Optional[str] = Field(default=None, description="Optional exact-match category filter.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.business_playbook import find_frameworks
            matches = find_frameworks(args.query, category=args.category)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        if not matches:
            return ToolResult(
                ok=True,
                output={"frameworks": [], "count": 0,
                        "note": "no matching framework — try a broader term or omit category"},
                metadata={"source": "business_playbook"},
            )

        return ToolResult(
            ok=True,
            output={
                "frameworks": [
                    {
                        "name": fw.name,
                        "category": fw.category,
                        "steps": list(fw.steps),
                        "principles": list(fw.principles),
                        "source": fw.source,
                    }
                    for fw in matches
                ],
                "count": len(matches),
            },
            metadata={"source": "business_playbook"},
        )
