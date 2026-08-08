"""
tools/mode_tools.py — Dynamic mode transitions (M35).

Three tools for in-session mode management:

  mode_status()           T0 — current mode, tier ceiling, pending override,
                               last 5 transitions in this session
  switch_mode(target_mode, reason)  T1 — Aria requests BUSY↔TIMED transition
                               (writes mode-override.json, loop reads it)
  request_mode_upgrade(target_mode, reason, duration_seconds)  T2 — operator-
                               confirmed upgrade to any mode

Safety:
  Autonomous transitions: BUSY↔TIMED only (both Tier ≤ T1 effective)
  Operator-confirmed: any mode via request_mode_upgrade (T2)
  BUSY tier ceiling (T1) is enforced by MODE_TIER_CEILING in modes.py —
  even if mode is switched to BUSY, tools above T1 remain withheld.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Allowed autonomous transitions (Aria can switch without operator approval)
_AUTO_ALLOWED: dict[str, set[str]] = {
    "busy": {"timed"},
    "timed": {"busy"},
}

_HISTORY_KEY = "_mode_history"  # stored in module-level list
_mode_history: list[dict] = []


class _StatusArgs(BaseModel):
    pass


class ModeStatusTool(Tool[_StatusArgs]):
    name = "mode_status"
    tier = 0
    description = (
        "Show the current session mode, tier ceiling, any pending mode override, "
        "and the last 5 mode transitions. Use this to understand what tier of tools "
        "are available and whether a mode switch is pending or in effect."
    )
    failure_modes = ("config_unreadable",)
    Args = _StatusArgs

    async def execute(self, args: _StatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.modes import MODE_TIER_CEILING, Mode
        override = _read_override(SETTINGS.paths.data_dir)
        current = _get_effective_mode()
        ceiling = MODE_TIER_CEILING.get(Mode(current), "unknown") if current else "unknown"
        return ToolResult(ok=True, output={
            "current_mode": current,
            "tier_ceiling": ceiling,
            "pending_override": override,
            "allowed_auto_transitions": list(_AUTO_ALLOWED.get(current or "", [])),
            "mode_history": _mode_history[-5:],
        })


class _SwitchArgs(BaseModel):
    target_mode: Literal["busy", "timed"] = Field(
        description="Target mode. Only busy↔timed transitions are autonomous.",
    )
    reason: str = Field(
        description="Why the mode switch is needed (recorded in history).",
        max_length=300,
    )


class SwitchModeTool(Tool[_SwitchArgs]):
    name = "switch_mode"
    tier = 1
    description = (
        "Request an autonomous mode switch (BUSY↔TIMED only). Writes a "
        "mode-override.json that the loop reads at the next iteration start. "
        "Override expires after 1 hour. BUSY mode caps tools at Tier 1 "
        "(the load-bearing safety design). Use to shift between background "
        "drain work (BUSY) and responsive single-task mode (TIMED)."
    )
    failure_modes = ("transition_not_allowed", "write_failed")
    Args = _SwitchArgs

    async def execute(self, args: _SwitchArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from sovereign_agent.config import SETTINGS
        current = _get_effective_mode() or "oneshot"
        allowed = _AUTO_ALLOWED.get(current, set())
        if args.target_mode not in allowed:
            return ToolResult(
                ok=False,
                error=(
                    f"Autonomous transition {current!r}→{args.target_mode!r} not allowed. "
                    f"Allowed from {current!r}: {sorted(allowed) or 'none'}. "
                    f"Use request_mode_upgrade() for operator-confirmed transitions."
                ),
            )
        override = {
            "target_mode": args.target_mode,
            "reason": args.reason,
            "requested_by": "aria",
            "expires_at": time.time() + 3600,
            "created_at": time.time(),
        }
        try:
            _write_override(SETTINGS.paths.data_dir, override)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write failed: {e}")
        _mode_history.append({
            "from": current,
            "to": args.target_mode,
            "reason": args.reason,
            "by": "aria",
            "at": time.time(),
        })
        return ToolResult(ok=True, output={
            "switched": True,
            "from_mode": current,
            "to_mode": args.target_mode,
            "expires_in_seconds": 3600,
        })


class _UpgradeArgs(BaseModel):
    target_mode: str = Field(description="Target mode: oneshot, timed, until, or busy.")
    reason: str = Field(description="Justification for the upgrade.", max_length=500)
    duration_seconds: int = Field(
        default=3600, ge=60, le=86400,
        description="How long the override should last (60s–24h).",
    )


class RequestModeUpgradeTool(Tool[_UpgradeArgs]):
    name = "request_mode_upgrade"
    tier = 2
    description = (
        "Request an operator-confirmed mode upgrade to any mode (oneshot, timed, "
        "until, busy). Requires operator confirmation (T2). Use when you need a "
        "mode that autonomous switch_mode() cannot provide."
    )
    failure_modes = ("invalid_mode", "write_failed")
    Args = _UpgradeArgs

    async def execute(self, args: _UpgradeArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.modes import Mode
        try:
            Mode(args.target_mode)
        except ValueError:
            valid = [m.value for m in Mode]
            return ToolResult(ok=False, error=f"invalid mode {args.target_mode!r}. Valid: {valid}")
        current = _get_effective_mode() or "oneshot"
        override = {
            "target_mode": args.target_mode,
            "reason": args.reason,
            "requested_by": "operator",
            "expires_at": time.time() + args.duration_seconds,
            "created_at": time.time(),
        }
        try:
            _write_override(SETTINGS.paths.data_dir, override)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write failed: {e}")
        _mode_history.append({
            "from": current,
            "to": args.target_mode,
            "reason": args.reason,
            "by": "operator",
            "at": time.time(),
        })
        return ToolResult(ok=True, output={
            "switched": True,
            "from_mode": current,
            "to_mode": args.target_mode,
            "duration_seconds": args.duration_seconds,
        })


# ── Internal helpers ──────────────────────────────────────────────────────────

def _override_path(data_dir: Path) -> Path:
    return data_dir / "mode_override.json"


def _read_override(data_dir: Path) -> dict | None:
    p = _override_path(data_dir)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if data.get("expires_at", 0) < time.time():
            p.unlink(missing_ok=True)
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def _write_override(data_dir: Path, override: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    _override_path(data_dir).write_text(json.dumps(override, indent=2))


def _get_effective_mode() -> str | None:
    """Try to get the current mode from the running loop's context."""
    import sovereign_agent.loop as _loop
    return getattr(_loop, "_current_mode_value", None)


__all__ = ["ModeStatusTool", "SwitchModeTool", "RequestModeUpgradeTool"]
