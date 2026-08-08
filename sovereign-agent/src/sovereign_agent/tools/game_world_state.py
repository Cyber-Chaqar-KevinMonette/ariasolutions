"""game_world_state.py — Tier 1. Poll a live-connected game's world state —
the structured perception channel for real-time co-play, not screenshots.

Kept at Tier 1 (not Tier 0) to match the other bridge tools it always pairs
with — Mode.BUSY's tier-1 ceiling must see all three (connect/place/state)
together or none of them, mid /work session.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..game_bridge_client import GameBridgeError, get_connection
from .base import Tool, ToolResult


class _Args(BaseModel):
    project_slug: str = Field(
        description="Slug of a registered game project — must already be "
                    "connected via game_bridge_connect"
    )
    since_seq: int = Field(default=0, description="Only return events/pieces newer than this sequence number")


class GameWorldStateTool(Tool[_Args]):
    name = "game_world_state"
    tier = 1
    description = (
        "Read the current placed-pieces world state, plus any pending "
        "unsolicited events (e.g. a human's placement pushed out live), "
        "from a live, connected game — over the real-time bridge (call "
        "game_bridge_connect first). Use this to perceive placement state "
        "during live co-play — take_screenshot/analyze_image are for "
        "aesthetic judgment, not for this. FAILURE MODES: not_connected; timeout."
    )
    failure_modes = ("not_connected", "timeout")
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        conn = get_connection(args.project_slug)
        if conn is None or not conn.connected:
            return ToolResult(ok=False, error="not_connected: call game_bridge_connect first")

        try:
            reply = await conn.send_command({"cmd": "get_world_state", "since_seq": args.since_seq})
        except GameBridgeError as e:
            return ToolResult(ok=False, error=str(e))

        pending_events = conn.poll_events(since_seq=args.since_seq)

        return ToolResult(ok=True, output={
            "pieces": reply.get("pieces", []),
            "seq": reply.get("seq", args.since_seq),
            "pending_events": pending_events,
        })


__all__ = ["GameWorldStateTool"]
