"""tools/recall_chunk_tool.py — Workstream P: the anti-compression recall
lever. Given a keyword (or a specific chunk id), returns the VERBATIM
original chunk content — never a summary. This is what a model reaches for
when it needs detail that scrolled out of the live context window, instead
of defaulting to lossy compress_context().

Modeled directly on RetrieveMemoryTool's/MemorySearchTool's existing
tool-exposure shape, just pointed at sealed chunks instead of atoms.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class RecallChunkTool(Tool):
    """Recall a sealed conversation checkpoint chunk, verbatim — the
    anti-compression lever. Prefer this over compress_context() when you
    need to remember something specific that scrolled out of view; fall
    back to compress_context() only if no chunk is granular enough, or you
    genuinely want a permanent condensed digest.

    FAILURE MODES: read_error
    """

    name = "recall_chunk"
    tier = 0
    description = (
        "Recall sealed conversation checkpoint chunks matching a keyword — "
        "returns the FULL ORIGINAL text of matching turns, never a summary. "
        "Try this before compress_context() when you need to remember "
        "something specific that scrolled out of the live context window."
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        keyword: str = Field(description="Substring to search sealed chunks for.")
        session_id: Optional[str] = Field(
            default=None, description="Restrict to one session, if known."
        )
        limit: int = Field(default=5, ge=1, le=50)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.checkpoint_chunks.index import ChunkIndex
            index = ChunkIndex()
            chunks = index.find_by_keyword(args.keyword, session_id=args.session_id)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        chunks = chunks[: args.limit]
        return ToolResult(
            ok=True,
            output={
                "count": len(chunks),
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "session_id": c.session_id,
                        "turn_range": [c.turn_start, c.turn_end],
                        "sealed_at": c.sealed_at,
                        "text": c.text(),
                    }
                    for c in chunks
                ],
            },
        )
