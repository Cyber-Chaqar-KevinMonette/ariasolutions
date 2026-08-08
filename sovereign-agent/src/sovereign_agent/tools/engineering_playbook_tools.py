"""tools/engineering_playbook_tools.py — read-only lookup over the curated index of
wondelai/skills software-engineering frameworks (Clean Code, DDIA, System Design, etc.)
in engineering_playbook.py.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class EngineeringPlaybookTool(Tool):
    """Look up curated software-engineering framework principles (Clean Code, Refactoring
    Patterns, Domain-Driven Design, System Design, Release It!, Team Topologies, etc.).

    Deterministic keyword match over a static, hand-curated index — not free-form LLM
    generation. Each result is an index entry (core principle + discipline names), not the
    full framework; every entry names the skill to invoke for full depth.

    FAILURE MODES: read_error
    """

    name = "engineering_playbook"
    tier = 0
    description = (
        "Look up curated software-engineering framework principles (e.g. clean code, refactoring, "
        "domain-driven design, system design, release-it resilience patterns, team topologies). "
        "query: free-text search term. category: optional exact-match filter "
        "(code-craftsmanship, systems-architecture). Returns matched principles with their core "
        "principle, key disciplines, and the skill to invoke for full depth. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        query: str = Field(default="", description="Free-text search term, e.g. 'circuit breaker' or 'ddd'.")
        category: Optional[str] = Field(default=None, description="Optional exact-match category filter.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.engineering_playbook import find_principles
            matches = find_principles(args.query, category=args.category)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        if not matches:
            return ToolResult(
                ok=True,
                output={"principles": [], "count": 0,
                        "note": "no matching principle — try a broader term or omit category"},
                metadata={"source": "engineering_playbook"},
            )

        return ToolResult(
            ok=True,
            output={
                "principles": [
                    {
                        "name": p.name,
                        "category": p.category,
                        "skill_slug": p.skill_slug,
                        "core_principle": p.core_principle,
                        "disciplines": list(p.disciplines),
                        "source": p.source,
                    }
                    for p in matches
                ],
                "count": len(matches),
            },
            metadata={"source": "engineering_playbook"},
        )
