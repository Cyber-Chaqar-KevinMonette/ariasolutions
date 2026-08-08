"""game_action_status.py — Tier 1. Check on a previously fired real-time
bridge command (game_place_piece with wait=False) without blocking.

Pairs with the decoupled think/act path added to game_bridge_client.py
(2026-08-03): fire_command() returns a req_id immediately; this tool is how
the reasoning loop later checks whether that command's reply has arrived,
without ever waiting on it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..game_bridge_client import get_connection
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_slug: str = Field(
        description="Slug of a registered game project — must already be "
                    "connected via game_bridge_connect"
    )
    req_id: str = Field(description="req_id returned by a prior game_place_piece(wait=False) call")


class GameActionStatusTool(Tool[_Args]):
    name = "game_action_status"
    tier = 1
    description = (
        "Check the result of a previously fired real-time action (from "
        "game_place_piece with wait=False) by its req_id — never blocks. "
        "Returns the game's reply if it has arrived, or status='pending' "
        "if not yet. FAILURE MODES: not_connected."
    )
    failure_modes = ("not_connected",)
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        conn = get_connection(args.project_slug)
        if conn is None or not conn.connected:
            return ToolResult(ok=False, error="not_connected: call game_bridge_connect first")

        reply = conn.check_result(args.req_id)
        if reply is None:
            return ToolResult(ok=True, output={"status": "pending"})

        return ToolResult(ok=True, output={"status": "resolved", **reply})


__all__ = ["GameActionStatusTool"]
