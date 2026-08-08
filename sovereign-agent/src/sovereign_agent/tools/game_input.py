"""game_input.py — Tier 1. Synthetic mouse/keyboard input via ydotool.

Kevin (2026-08-03): "give her the same tools and abilities you are using
if you can" — said after watching a real click land in the Ember Keep
Play window, driven by hand via ydotool during a live playtest. Explicit
choice on standing autonomy, after being told the tradeoff: Tier 1, no
per-call approval gate. Worth naming plainly since it's a real
departure from this project's usual "powerful capability defaults to
Tier 3" posture — unlike the game-dev tools, synthetic OS-level input
is NOT sandboxed to the Godot window. It can click or type anywhere on
the real desktop. Kevin chose speed over the approval gate here
knowingly; if that judgment ever needs revisiting, this is the tool to
re-tier, not to quietly work around.

Requires ydotoold running — a background daemon that owns a uinput
device. Installed and started live 2026-08-03: `sudo apt install
ydotool ydotoold`, this user added to the `input` group, `ydotoold &`.
This tool does NOT start the daemon itself; if it's not running, every
call fails loudly with daemon_unreachable, never silently.

Absolute positioning: this ydotool build's `mousemove` is RELATIVE ONLY
(confirmed live — no -a/--absolute flag exists in the installed
0.1.8-3build1). click_at/move_absolute work around that the same way it
was proven live: a large negative relative move first (clamped at the
screen's top-left corner by the OS pointer boundary), then an exact
relative move to the target coordinates. Chain with take_screenshot
first to find real target coordinates — don't guess them.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_YDOTOOL_CMD = "ydotool"
_SOCKET_PATH = Path("/tmp/.ydotool_socket")
_TIMEOUT = 10
# Larger than any real display — guarantees the homing move clamps the
# cursor to screen (0,0) regardless of actual resolution.
_HOME_OFFSET = 10000


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=_TIMEOUT, stdin=subprocess.DEVNULL,
    )


class _Args(BaseModel):
    action: Literal["click", "click_at", "move_relative", "move_absolute", "key"] = Field(
        description=(
            "click: click at wherever the cursor already is. click_at: move "
            "to an absolute screen x,y then click (needs x, y). "
            "move_relative: nudge the cursor by dx,dy from its current "
            "position (needs dx, dy). move_absolute: move the cursor to an "
            "exact screen x,y (needs x, y). key: send a key sequence, e.g. "
            "'F5' or 'ctrl+s' (needs keys)."
        )
    )
    x: Optional[int] = Field(default=None, description="Target x, screen pixels (click_at/move_absolute)")
    y: Optional[int] = Field(default=None, description="Target y, screen pixels (click_at/move_absolute)")
    dx: Optional[int] = Field(default=None, description="Relative x delta, pixels (move_relative)")
    dy: Optional[int] = Field(default=None, description="Relative y delta, pixels (move_relative)")
    button: int = Field(default=1, ge=1, le=3, description="1=left 2=right 3=middle (click/click_at)")
    keys: Optional[str] = Field(default=None, description="Key sequence for the key action, e.g. 'F5'")


class GameInputTool(Tool[_Args]):
    name = "game_input"
    tier = 1
    description = (
        "Send a real synthetic mouse click/move or keypress to whatever has "
        "focus on the real desktop, via ydotool — the same mechanism used to "
        "actually playtest a running game (e.g. click the fire to tend it, "
        "press F5 to launch Play). NOT sandboxed to any single window — it "
        "goes wherever the OS currently has focus, so take_screenshot first "
        "to confirm the right window is focused before clicking. "
        "FAILURE MODES: ydotool_not_found; daemon_unreachable; missing_args; "
        "invalid_action; subprocess_error."
    )
    failure_modes = (
        "ydotool_not_found",
        "daemon_unreachable",
        "missing_args",
        "invalid_action",
        "subprocess_error",
    )
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        if shutil.which(_YDOTOOL_CMD) is None:
            return ToolResult(
                ok=False,
                error="ydotool_not_found: install with `sudo apt install ydotool ydotoold`",
            )
        if not _SOCKET_PATH.exists():
            return ToolResult(
                ok=False,
                error=f"daemon_unreachable: {_SOCKET_PATH} not found — start ydotoold first",
            )

        try:
            result = self._dispatch(args)
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error="subprocess_error: ydotool timed out")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"subprocess_error: {exc!r}")

        if isinstance(result, ToolResult):
            return result

        r, summary = result
        if r.returncode != 0:
            return ToolResult(
                ok=False,
                error=f"subprocess_error: exit {r.returncode}: {r.stderr.strip()}",
            )
        return ToolResult(
            ok=True,
            output={
                "action": args.action,
                **summary,
                "next": "take_screenshot to confirm the result",
            },
        )

    def _dispatch(self, args: _Args):
        if args.action == "click":
            r = _run([_YDOTOOL_CMD, "click", str(args.button)])
            return r, {"button": args.button}

        if args.action == "click_at":
            if args.x is None or args.y is None:
                return ToolResult(ok=False, error="missing_args: click_at requires x and y")
            home = _run([_YDOTOOL_CMD, "mousemove", "--", str(-_HOME_OFFSET), str(-_HOME_OFFSET)])
            if home.returncode != 0:
                return ToolResult(
                    ok=False,
                    error=f"subprocess_error: homing move failed: {home.stderr.strip()}",
                )
            move = _run([_YDOTOOL_CMD, "mousemove", str(args.x), str(args.y)])
            if move.returncode != 0:
                return ToolResult(
                    ok=False,
                    error=f"subprocess_error: move-to-target failed: {move.stderr.strip()}",
                )
            r = _run([_YDOTOOL_CMD, "click", str(args.button)])
            return r, {"x": args.x, "y": args.y, "button": args.button}

        if args.action == "move_relative":
            if args.dx is None or args.dy is None:
                return ToolResult(ok=False, error="missing_args: move_relative requires dx and dy")
            r = _run([_YDOTOOL_CMD, "mousemove", "--", str(args.dx), str(args.dy)])
            return r, {"dx": args.dx, "dy": args.dy}

        if args.action == "move_absolute":
            if args.x is None or args.y is None:
                return ToolResult(ok=False, error="missing_args: move_absolute requires x and y")
            home = _run([_YDOTOOL_CMD, "mousemove", "--", str(-_HOME_OFFSET), str(-_HOME_OFFSET)])
            if home.returncode != 0:
                return ToolResult(
                    ok=False,
                    error=f"subprocess_error: homing move failed: {home.stderr.strip()}",
                )
            r = _run([_YDOTOOL_CMD, "mousemove", str(args.x), str(args.y)])
            return r, {"x": args.x, "y": args.y}

        if args.action == "key":
            if not args.keys:
                return ToolResult(ok=False, error="missing_args: key requires keys")
            r = _run([_YDOTOOL_CMD, "key", args.keys])
            return r, {"keys": args.keys}

        return ToolResult(ok=False, error=f"invalid_action: {args.action!r}")


__all__ = ["GameInputTool"]
