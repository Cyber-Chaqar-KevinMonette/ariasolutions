"""tools/tool_paging.py — request_tools: dynamic tool paging within authority.

THE GAP (Keys round K5): the prompt diet keeps requests inside the 8B
model's context window by sending a curated 18-tool core (plus any tool
named verbatim in the goal). `list_available_tools` let the model DISCOVER
the other ~200 tools — but discovery without attachment was a dead end:
it could see the names and never call them.

`request_tools(names)` closes the pair: the model asks for tools by name,
and the loop attaches their schemas for the REST OF THE RUN. Bounded and
authority-safe by construction:
  - the loop only ever attaches tools that the AUTHORITY GATE already
    allowed for this mode (the same `available` meta-list the loop was
    built from) — paging can never smuggle a tool past the tier ceiling;
  - at most MAX_NAMES_PER_CALL names per call, MAX_PAGED_TOTAL paged
    tools per run — the schema budget stays inside the context window;
  - a `tool-paged-d` event records every attachment (observable in the
    cockpit's live pane via K1).

This tool itself only VALIDATES AND PROPOSES (returns the granted list in
its metadata); the loop performs the attachment — the tool has no reach
into the loop's internals.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

MAX_NAMES_PER_CALL = 10
MAX_PAGED_TOTAL = 40


class RequestToolsTool(Tool):
    """Ask for named tools' schemas to be attached for the rest of this run.

    FAILURE MODES: none_granted
    """

    name = "request_tools"
    tier = 0
    description = (
        "Attach the schemas of named tools for the rest of this run. Use "
        "list_available_tools first to discover what exists, then request "
        "exactly what you need by name (max "
        f"{MAX_NAMES_PER_CALL} per call). Only tools your current mode's "
        "authority tier already allows will attach. "
        "FAILURE MODES: none_granted"
    )
    failure_modes = ("none_granted",)

    class Args(BaseModel):
        names: list[str] = Field(
            ..., min_length=1, max_length=MAX_NAMES_PER_CALL,
            description="Exact tool names to attach (from list_available_tools).",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.authority import _TIER_REGISTRY

        granted: list[str] = []
        unknown: list[str] = []
        for name in dict.fromkeys(args.names):  # dedupe, keep order
            if name in _TIER_REGISTRY:
                granted.append(name)
            else:
                unknown.append(name)
        if not granted:
            return ToolResult(
                ok=False,
                error=f"none_granted: no requested name exists — unknown: {unknown}",
            )
        note = (
            "attached for the rest of this run (authority-gated: names your "
            "mode's tier ceiling withholds will not attach)"
        )
        return ToolResult(
            ok=True,
            output={"granted": granted, "unknown": unknown, "note": note},
            metadata={"granted": granted, "unknown": unknown,
                      "source": "request_tools"},
        )
