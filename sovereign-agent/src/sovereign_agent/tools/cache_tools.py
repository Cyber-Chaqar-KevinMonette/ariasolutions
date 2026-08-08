"""
tools/cache_tools.py — Cache inspection and control tools (M33).

  cache_stats()          T0 — show hit rate, size, tokens saved this session
  cache_flush(tool_name) T1 — clear cache for all tools or one named tool
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _StatsArgs(BaseModel):
    pass


class CacheStatsTool(Tool[_StatsArgs]):
    name = "cache_stats"
    tier = 0
    description = (
        "Show T0 tool cache statistics for this session: hit rate, size, "
        "tokens saved estimate, entries by tool. Use this to understand how "
        "much redundant work the cache is eliminating."
    )
    failure_modes = ("cache_not_initialized",)
    Args = _StatsArgs

    async def execute(self, args: _StatsArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from sovereign_agent.cache import ResponseCache
        cache = _get_cache()
        return ToolResult(ok=True, output=cache.stats())


class _FlushArgs(BaseModel):
    tool_name: Optional[str] = Field(
        default=None,
        description="Name of tool to flush. Omit to flush all cached results.",
    )


class CacheFlushTool(Tool[_FlushArgs]):
    name = "cache_flush"
    tier = 1
    description = (
        "Clear cached results for one tool (tool_name=...) or all tools "
        "(tool_name omitted). Returns the number of entries cleared. "
        "Use when you know a data source has changed and you need fresh results."
    )
    failure_modes = ("cache_not_initialized",)
    Args = _FlushArgs

    async def execute(self, args: _FlushArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        cache = _get_cache()
        count = cache.flush(args.tool_name)
        return ToolResult(ok=True, output={"cleared": count, "tool_name": args.tool_name})


def _get_cache():
    """Get the module-level ResponseCache instance from loop.py."""
    import sovereign_agent.loop as _loop
    cache = getattr(_loop, "_response_cache", None)
    if cache is None:
        from sovereign_agent.cache import ResponseCache
        cache = ResponseCache()
    return cache


__all__ = ["CacheStatsTool", "CacheFlushTool"]
