"""memory_search — Tier 0 (read-only retrieval).

Hybrid retrieval over atoms.db: vector ANN + FTS5, fused via Reciprocal
Rank Fusion. Returns hydrated atom summaries with both ranks visible so
the agent can reason about why a result appeared.
"""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..db import open_atoms_db
from ..memory import hybrid_search
from ..ollama_client import OllamaClient
from .base import Tool, ToolResult


class _Args(BaseModel):
    query: str = Field(description="Free-text query — embedded and FTS-matched", min_length=1)
    top_k: int = Field(default=10, ge=1, le=50, description="How many results to return")


class MemorySearchTool(Tool[_Args]):
    name = "memory_search"
    tier = 0
    description = (
        "Search atoms.db with hybrid retrieval (vector + FTS, RRF fused). "
        "Returns top_k atoms with summary, type, confidence, and both ranks. "
        "Use this BEFORE making decisions to ground them in prior runs. "
        "FAILURE MODES: ollama unreachable (embedding fails); empty result set; "
        "FTS5 not available; vec_atoms empty."
    )
    failure_modes = (
        "ollama_unreachable",
        "no_results",
        "fts_unavailable",
        "vec_index_empty",
    )
    Args = _Args

    def __init__(self, client: OllamaClient | None = None) -> None:
        self._client = client or OllamaClient()

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        # Embed the query in the async context first, then hand the synchronous
        # DB call off to a worker thread.
        try:
            query_vec = await self._client.embed(
                model=SETTINGS.embed_model, prompt=args.query
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"embedding failed: {e}")

        def _search() -> list[dict]:
            conn = open_atoms_db()
            try:
                hits = hybrid_search(conn, args.query, query_vec=query_vec, top_k=args.top_k)
                return [
                    {
                        "atom_id": h.atom_id,
                        "summary": h.summary,
                        "fused_score": round(h.fused_score, 6),
                        "vec_rank": h.vec_rank,
                        "fts_rank": h.fts_rank,
                        "metadata": h.metadata,
                    }
                    for h in hits
                ]
            finally:
                conn.close()

        try:
            results = await asyncio.to_thread(_search)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"search failed: {e}")

        return ToolResult(
            ok=True,
            output=results,
            metadata={"query": args.query, "count": len(results)},
        )
