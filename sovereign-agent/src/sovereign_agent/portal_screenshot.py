"""portal_screenshot.py — org.freedesktop.portal.Screenshot client.

Same root cause as portal_screencast.py's screen-recording fix (2026-08-02):
this machine's compositor is COSMIC, which doesn't implement grim's protocol
(wlr-screencopy-unstable-v1). Reproduced live here too: `grim` isn't even on
PATH, and vision_capture()/take_screenshot() were silently returning
ok=True with zero text/no screenshot_path instead of a real error — a
dishonest success, not a loud failure (CLAUDE.md's honesty doctrine).

The portal's Screenshot interface is the single-call sibling of ScreenCast:
one Screenshot(parent_window, options) request, one Response signal
carrying a `uri` (a file:// path to an already-saved PNG) — no PipeWire
negotiation needed, so this reuses portal_screencast.py's proven bus/
request/response plumbing directly rather than re-deriving it.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from .portal_screencast import (
    _BUS_NAME,
    _OBJ_PATH,
    _REQUEST_IFACE,  # noqa: F401 — re-exported implicitly via shared helpers
    _RESPONSE_TIMEOUT_S,
    _connect_bus,
    _register_response_waiter,
    _request_path,
    _unwrap,
    _wait_for_response,
    portal_available,
)

__all__ = ["capture_screenshot_via_portal", "portal_available"]

_SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
# One-time consent dialog is possible on first-ever call per compositor;
# generous but bounded so an automated caller doesn't hang forever.
_SCREENSHOT_TIMEOUT_S = 30.0


def _uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    return Path(unquote(parsed.path))


async def capture_screenshot_via_portal() -> Optional[Path]:
    """Request a screenshot through the desktop portal. Returns the saved
    PNG's path, or None if the portal is unreachable/denied/unavailable —
    mirrors capture_screenshot()'s own "return None, don't raise" contract
    so vision.py can fall back to grim (or vice versa) without a caller
    needing to know which backend actually worked."""
    if not portal_available():
        return None
    try:
        bus = await _connect_bus()
    except Exception:  # noqa: BLE001 — no session bus, no portal, etc.
        return None

    try:
        from dbus_next import Message, Variant

        token = "sov" + secrets.token_hex(8)
        request_path = _request_path(bus, token)
        options = {
            "handle_token": Variant("s", token),
            "interactive": Variant("b", False),
        }
        fut, handler = _register_response_waiter(bus, request_path)
        msg = Message(destination=_BUS_NAME, path=_OBJ_PATH, interface=_SCREENSHOT_IFACE,
                      member="Screenshot", signature="sa{sv}", body=["", options])
        reply = await bus.call(msg)
        if reply.error_name:
            bus.remove_message_handler(handler)
            return None

        code, results = await _wait_for_response(
            bus, fut, handler, timeout=_SCREENSHOT_TIMEOUT_S)
        if code != 0 or "uri" not in results:
            return None
        return _uri_to_path(str(_unwrap(results["uri"])))
    except Exception:  # noqa: BLE001 — best-effort capture, never raises
        return None
    finally:
        try:
            bus.disconnect()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass
