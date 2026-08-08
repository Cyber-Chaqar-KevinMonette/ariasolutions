"""embed_query — Tier 0. Produces an embedding for a query string."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..ollama_client import OllamaClient
from .base import Tool, ToolResult


class _Args(BaseModel):
    text: str = Field(description="Text to embed", min_length=1, max_length=8000)


class EmbedQueryTool(Tool[_Args]):
    name = "embed_query"
    tier = 0
    description = (
        "Produce a 768-dim embedding (nomic-embed-text) for a query string. Use "
        "this before memory_search if you need to perform semantic retrieval over "
        "the atom store. FAILURE MODES: Ollama unreachable; embedding model not "
        "pulled; input exceeds model context (8192 tokens for nomic)."
    )
    failure_modes = (
        "ollama_unreachable",
        "model_not_pulled",
        "context_exceeded",
    )
    Args = _Args

    def __init__(self, client: OllamaClient | None = None) -> None:
        self._client = client or OllamaClient()

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            vec = await self._client.embed(model=SETTINGS.embed_model, prompt=args.text)
            return ToolResult(
                ok=True,
                output=vec,
                metadata={"dim": len(vec), "model": SETTINGS.embed_model},
            )
        except Exception as e:  # noqa: BLE001 — surface as tool error, don't crash loop
            return ToolResult(ok=False, error=f"embedding failed: {type(e).__name__}: {e}")
