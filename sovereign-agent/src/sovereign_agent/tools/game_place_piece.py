"""game_place_piece.py — Tier 1. Place a piece in a live-connected game's
world, over the real-time bridge — not a screenshot+click action.

This is how Aria actually builds alongside a human player in real time.
Requires game_bridge_connect first. See game_bridge_client.py's module
docstring for the wire protocol and the reasoning for this whole approach.

wait=True (default) preserves the original blocking behavior exactly —
awaits the game's reply before returning, same as always. wait=False is the
new decoupled path (2026-08-03): fires the placement and returns the req_id
immediately, without waiting on the game's reply, so the reasoning loop
never stalls on a round-trip — check the outcome later with
game_action_status. Default stays True rather than flipping so existing
callers/behavior don't silently change; use wait=False deliberately for
real-time co-play.
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
    x: int = Field(description="Grid x coordinate")
    y: int = Field(description="Grid y coordinate")
    z: int = Field(default=0, description="Grid z coordinate (0 for a 2D project)")
    piece_type: str = Field(description="Which piece to place, e.g. 'wall', 'floor', 'torch'")
    wait: bool = Field(
        default=True,
        description="True (default): block until the game confirms the "
                    "placement, return its reply. False: fire the command "
                    "and return immediately with a req_id — don't block the "
                    "reasoning loop; check the outcome later with "
                    "game_action_status.",
    )


class GamePlacePieceTool(Tool[_Args]):
    name = "game_place_piece"
    tier = 1
    description = (
        "Place a piece at a grid cell in a live, connected game's world — "
        "sent over the real-time bridge (call game_bridge_connect first), "
        "not a screenshot+click. This is the real-time co-play action. Set "
        "wait=False to fire-and-continue without blocking on the game's "
        "reply (check later with game_action_status) — use this for "
        "fast-paced live co-play. "
        "FAILURE MODES: not_connected; invalid_piece_type; cell_occupied; timeout."
    )
    failure_modes = ("not_connected", "invalid_piece_type", "cell_occupied", "timeout")
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        conn = get_connection(args.project_slug)
        if conn is None or not conn.connected:
            return ToolResult(ok=False, error="not_connected: call game_bridge_connect first")

        cmd = {
            "cmd": "place_piece",
            "x": args.x, "y": args.y, "z": args.z,
            "piece_type": args.piece_type,
            "actor": "aria",
        }

        if not args.wait:
            try:
                req_id = await conn.fire_command(cmd)
            except GameBridgeError as e:
                return ToolResult(ok=False, error=str(e))
            return ToolResult(ok=True, output={"req_id": req_id, "status": "fired"})

        try:
            reply = await conn.send_command(cmd)
        except GameBridgeError as e:
            return ToolResult(ok=False, error=str(e))

        if reply.get("event") == "error":
            reason = reply.get("reason", "unknown")
            return ToolResult(ok=False, error=f"{reason}: {reply.get('detail', '')}")

        return ToolResult(ok=True, output=reply)


__all__ = ["GamePlacePieceTool"]
