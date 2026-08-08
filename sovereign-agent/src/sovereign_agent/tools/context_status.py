"""tools/context_status.py — Aria's own context-health introspection.

Kevin, 2026-08-02: "give aria a token optimizing system" — not just a
human-facing cockpit gauge, the same numbers available to her directly.
Mirrors tools/resilience_tools.py's exact shape (T0, no args, reads
already-computed state rather than performing a new measurement).

Tools run outside the cockpit process, so this can't read
CockpitApp._session_tokens directly — instead it reads the same source
of truth the cockpit's own status bar does: the latest token-usage-d
event in today's events.jsonl (read_repair.py's shared tolerant NDJSON
reader, same as every other store in this codebase uses).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .base import Tool, ToolResult


class _Args(BaseModel):
    pass


class ContextStatusTool(Tool[_Args]):
    name = "context_status"
    tier = 0
    description = (
        "Show context-window and run-budget health as 0-100% gauges: how "
        "close the last request came to the model's num_ctx window "
        "(compact when high), and how much of this task's cumulative "
        "token budget has been spent (consider /clear-session when high). "
        "Reads the latest token-usage-d event — real numbers, not a guess."
    )
    failure_modes = ("no_events_yet",)
    Args = _Args

    def __init__(self, events_path: Path | None = None) -> None:
        self._events_path = events_path

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from ..config import SETTINGS
        from ..context_health import assess
        from ..modes import RunBudget
        from ..read_repair import read_ndjson_tolerant

        num_ctx = SETTINGS.num_ctx
        max_tokens = RunBudget().max_tokens
        events_path = self._events_path or SETTINGS.paths.events_jsonl

        result = read_ndjson_tolerant(events_path, store="context_status", emit=False)

        prompt_tokens = 0
        running_total = 0
        found = False
        for rec in reversed(result.records):
            if rec.get("flag") == "token-usage-d":
                payload = rec.get("payload") or {}
                prompt_tokens = int(payload.get("prompt_tokens", 0))
                running_total = int(payload.get("running_total", 0))
                found = True
                break

        health = assess(prompt_tokens, running_total, num_ctx=num_ctx, max_tokens=max_tokens)
        output = health.as_dict()
        output.update({
            "prompt_tokens": prompt_tokens,
            "running_total": running_total,
            "num_ctx": num_ctx,
            "max_tokens": max_tokens,
        })
        if not found:
            output["note"] = "no token-usage-d events found yet today — nothing has run"
        return ToolResult(ok=True, output=output)


__all__ = ["ContextStatusTool"]
