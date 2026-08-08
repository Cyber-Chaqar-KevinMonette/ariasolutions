"""tools/notify_tools.py — Desktop Notifications via DBus (M51).

  notify(title, body, urgency, icon, timeout_ms)    T0 — send desktop notification
  notify_status()                                    T0 — check notification daemon availability
"""
from __future__ import annotations

import asyncio
import subprocess
from typing import Literal

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# DBus destination for freedesktop notifications
_NOTIFY_DEST = "org.freedesktop.Notifications"
_NOTIFY_PATH = "/org/freedesktop/Notifications"
_NOTIFY_IFACE = "org.freedesktop.Notifications"


def _gdbus_available() -> bool:
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", _NOTIFY_DEST,
             "--object-path", _NOTIFY_PATH,
             "--method", f"{_NOTIFY_IFACE}.GetServerInformation"],
            capture_output=True, text=True, timeout=3,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _send_notification(title: str, body: str, icon: str, timeout_ms: int) -> bool:
    """Send via gdbus call to org.freedesktop.Notifications.Notify."""
    try:
        result = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", _NOTIFY_DEST,
                "--object-path", _NOTIFY_PATH,
                "--method", f"{_NOTIFY_IFACE}.Notify",
                "Aria",           # app_name
                "0",              # replaces_id
                icon,             # app_icon
                title,            # summary
                body,             # body
                "[]",             # actions
                "{}",             # hints
                str(timeout_ms),  # expire_timeout (ms)
            ],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False


# ── notify ────────────────────────────────────────────────────────────────────


class _NotifyArgs(BaseModel):
    title: str = Field(max_length=200, description="Notification title.")
    body: str = Field(default="", max_length=1000, description="Notification body text.")
    urgency: Literal["low", "normal", "critical"] = Field(
        default="normal",
        description="Urgency level: low (5s), normal (10s), critical (persistent).",
    )
    icon: str = Field(
        default="dialog-information",
        description=(
            "Icon name. Common: dialog-information, dialog-warning, "
            "dialog-error, appointment-new, task-due."
        ),
    )


class NotifyTool(Tool[_NotifyArgs]):
    name = "notify"
    tier = 0
    description = (
        "Send a desktop notification via the freedesktop DBus notification protocol. "
        "Uses gdbus — works with cosmic-notifications on Pop!_OS (and any "
        "freedesktop-compliant notification daemon). "
        "Use this to alert Kevin when long-running work completes, or for important "
        "status updates when he may not be watching the cockpit."
    )
    failure_modes = ("dbus_unavailable", "notification_failed")
    Args = _NotifyArgs

    async def execute(self, args: _NotifyArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            timeout_ms = {"low": 5000, "normal": 10000, "critical": 0}[args.urgency]
            icon = args.icon
            if args.urgency == "critical" and icon == "dialog-information":
                icon = "dialog-warning"

            sent = await asyncio.to_thread(
                _send_notification, args.title, args.body, icon, timeout_ms
            )
            if not sent:
                return ToolResult(
                    ok=False,
                    error=(
                        "Desktop notification failed. "
                        "gdbus/freedesktop notification daemon may not be available."
                    ),
                )
            return ToolResult(ok=True, output={
                "title": args.title,
                "body": args.body,
                "urgency": args.urgency,
                "icon": icon,
                "timeout_ms": timeout_ms,
                "message": f"Notification sent: {args.title!r}",
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"notify failed: {e}")


# ── notify_status ─────────────────────────────────────────────────────────────


class _NotifyStatusArgs(BaseModel):
    pass


class NotifyStatusTool(Tool[_NotifyStatusArgs]):
    name = "notify_status"
    tier = 0
    description = (
        "Check if the desktop notification daemon is available. "
        "Returns server name, vendor, and version. "
        "Call before relying on notify() for critical alerts."
    )
    failure_modes = ("dbus_unavailable",)
    Args = _NotifyStatusArgs

    async def execute(self, args: _NotifyStatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["gdbus", "call", "--session",
                 "--dest", _NOTIFY_DEST,
                 "--object-path", _NOTIFY_PATH,
                 "--method", f"{_NOTIFY_IFACE}.GetServerInformation"],
                capture_output=True, text=True, timeout=3,
            )
            available = result.returncode == 0
            info = result.stdout.strip() if available else None
            return ToolResult(ok=True, output={
                "available": available,
                "server_info": info,
                "backend": "gdbus → org.freedesktop.Notifications",
                "note": (
                    "Notification daemon ready."
                    if available else
                    "No notification daemon found on DBus session."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"notify_status failed: {e}")


__all__ = [
    "NotifyTool",
    "NotifyStatusTool",
]
