"""palace_search — Tier 0. Search the palace's closet index from inside an agent step.

Pairs with the existing ``memory_search`` (which queries atoms.db) — but
operates on the structured layer instead. Useful when the agent needs to
ask "what does the canon say about rollback?" or "have I already filed an
insight about this?" during a reflection step.

Returns up to ``max_results`` closets matching a substring query against
topic + entities. Scoped to a specific room with ``room_id``.

Authority tier 0 — read-only.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _Args(BaseModel):
    query: str = Field(min_length=1, max_length=300,
                       description="Substring to match in closet topics or entities.")
    room_id: str | None = Field(
        default=None,
        description="Optional: scope to a specific room (e.g. 'room-mos-canon').",
    )
    max_results: int = Field(default=5, ge=1, le=20)


class PalaceSearchTool(Tool[_Args]):
    name = "palace_search"
    tier = 0
    description = (
        "Search the palace's closet index. Returns matching topics with their "
        "entity tags and source atom ids. Use this to consult structured memory "
        "(MOS canon clauses, prior insights, mined corpus structure) from inside "
        "an agent step. Read-only. FAILURE MODES: palace_unavailable; query_invalid."
    )
    failure_modes = ("palace_unavailable", "query_invalid")
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from ..palace import open_palace
            p = open_palace()
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"palace_unavailable: {e}")

        try:
            results = p.search_closets_keyword(
                args.query, limit=args.max_results, room_id=args.room_id,
            )
        finally:
            p.close()

        if not results:
            return ToolResult(
                ok=True,
                output=[],
                metadata={"query": args.query, "room_id": args.room_id, "count": 0},
            )

        rendered = [
            {
                "id": c.id,
                "room_id": c.room_id,
                "topic": c.topic,
                "entities": c.entities,
                "atom_ids": c.atom_ids,
            }
            for c in results
        ]
        return ToolResult(
            ok=True,
            output=rendered,
            metadata={"query": args.query, "room_id": args.room_id, "count": len(rendered)},
        )
