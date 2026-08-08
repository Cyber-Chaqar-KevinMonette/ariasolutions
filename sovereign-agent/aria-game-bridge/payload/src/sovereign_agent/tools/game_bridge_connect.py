"""game_bridge_connect.py — Tier 1. Open the live real-time bridge
connection to a running game's Godot-side socket server.

The fast, structured path for real-time co-play — see game_bridge_client.py's
module docstring for the full rationale (screenshots are too slow/fragile
for this; this is a direct TCP/NDJSON channel to a running game_bridge.gd
autoload). Tier 1, not higher: Mode.BUSY (the default /work session mode)
caps the visible toolset at tier 1, and a per-call approval gate on a
real-time connection would defeat the point.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_bridge_client import GameBridgeError, connect as _bridge_connect, get_connection
from ..game_projects import load_by_slug
from .godot_open import godot_gui_pids
from .base import Tool, ToolResult

_DEFAULT_PORT = 8781


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")
    port: int = Field(default=_DEFAULT_PORT, description="TCP port the game's bridge server is listening on")


class GameBridgeConnectTool(Tool[_Args]):
    name = "game_bridge_connect"
    tier = 1
    description = (
        "Open a live, persistent TCP/NDJSON connection to a running game's "
        "real-time bridge server (its game_bridge.gd autoload) — the fast "
        "path for perceiving and acting on world state during live co-play, "
        "instead of screenshots. Idempotent: returns the existing connection "
        "if already connected. The game must already be running (godot_open, "
        "or F5 inside an open editor) with its bridge autoload listening. "
        "Call this before game_place_piece or game_world_state. "
        "FAILURE MODES: unknown_project; godot_not_running; connection_refused; timeout."
    )
    failure_modes = ("unknown_project", "godot_not_running", "connection_refused", "timeout")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        if load_by_slug(args.project_slug, data_dir) is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        existing = get_connection(args.project_slug)
        if existing is not None and existing.connected:
            return ToolResult(ok=True, output={"already_connected": True, "project_slug": args.project_slug})

        if not godot_gui_pids():
            return ToolResult(
                ok=False,
                error="godot_not_running: no Godot GUI instance detected — launch it first (godot_open)",
            )

        try:
            await _bridge_connect(args.project_slug, port=args.port)
        except ConnectionRefusedError:
            return ToolResult(
                ok=False,
                error="connection_refused: Godot is running but nothing is listening on "
                      f"port {args.port} — is game_bridge.gd registered as an autoload?",
            )
        except GameBridgeError as e:
            return ToolResult(ok=False, error=str(e))
        except OSError as e:
            return ToolResult(ok=False, error=f"connection_refused: {e!r}")

        return ToolResult(ok=True, output={"already_connected": False, "project_slug": args.project_slug})


__all__ = ["GameBridgeConnectTool"]
