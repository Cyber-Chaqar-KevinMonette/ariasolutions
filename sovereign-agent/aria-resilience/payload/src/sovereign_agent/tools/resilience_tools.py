"""
tools/resilience_tools.py — Circuit breaker status inspection (M34).

  resilience_status() T0 — all circuit breakers: name, state, failure_count,
    last_failure_at. Use this to see which tools or LLM connections are
    currently OPEN or strained, and when they will recover.
"""
from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolResult


class _Args(BaseModel):
    pass


class ResilienceStatusTool(Tool[_Args]):
    name = "resilience_status"
    tier = 0
    description = (
        "Show the state of all circuit breakers in this session: which tools "
        "or LLM connections are CLOSED (normal), OPEN (failing — calls blocked), "
        "or HALF_OPEN (recovery probe). Use this to understand failure patterns "
        "and when a blocked resource will recover."
    )
    failure_modes = ("registry_not_initialized",)
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        registry = _get_registry()
        statuses = registry.all_statuses()
        open_count = sum(1 for s in statuses if s["state"] == "open")
        return ToolResult(ok=True, output={
            "breakers": statuses,
            "total": len(statuses),
            "open": open_count,
            "healthy": len(statuses) - open_count,
        })


def _get_registry():
    import sovereign_agent.loop as _loop
    reg = getattr(_loop, "_breaker_registry", None)
    if reg is None:
        from sovereign_agent.resilience import BreakerRegistry
        reg = BreakerRegistry()
    return reg


__all__ = ["ResilienceStatusTool"]
