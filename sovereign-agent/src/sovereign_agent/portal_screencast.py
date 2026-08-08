"""portal_screencast.py — org.freedesktop.portal.ScreenCast client.

Kevin, 2026-08-02: screen recording fails every time ("no playable file
was written"). Reproduced live: this machine's compositor is COSMIC,
which doesn't implement `wlr-screencopy-unstable-v1` — the only protocol
`wf-recorder` (cockpit/screen_recording_session.py's old backend) speaks.
COSMIC ships `xdg-desktop-portal-cosmic`, so the real fix is the standard
portal path every modern compositor (GNOME/KDE/COSMIC) supports:
CreateSession -> SelectSources -> Start -> OpenPipeWireRemote, then hand
the returned PipeWire node to a real capture pipeline (see
cockpit/screen_recording_session.py, which now uses gst-launch-1.0's
`pipewiresrc` instead of wf-recorder).

Uses dbus-next (pure-Python asyncio D-Bus, no GLib mainloop needed) at
the raw Message level rather than its introspection-driven dynamic proxy
API — deliberate: the portal's interface/method/signature strings are a
stable, documented spec (this module IS that spec, hand-transcribed), so
a live introspection round-trip buys nothing but an extra failure mode,
and raw Message calls are what let tests monkeypatch each step
independently without faking dbus-next's introspection machinery.

The CreateSession -> SelectSources round-trip and the Response-signal
plumbing were verified LIVE on this machine (deterministic request-path
computation matched the real portal's reply exactly, no AddMatch call
needed — dbus-next's aio MessageBus receives it regardless). `Start()`
and `OpenPipeWireRemote()` could NOT be verified the same way — `Start()`
blocks on a real interactive OS picker dialog (by design: the portal
model requires user consent) that nothing in this tool environment can
click through. Kevin does the first real end-to-end run.
"""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Any

__all__ = ["ScreenCastSession", "request_screencast_session", "portal_available"]

_BUS_NAME = "org.freedesktop.portal.Desktop"
_OBJ_PATH = "/org/freedesktop/portal/desktop"
_SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
_REQUEST_IFACE = "org.freedesktop.portal.Request"
_SESSION_IFACE = "org.freedesktop.portal.Session"

_SOURCE_TYPE_MONITOR = 1  # ScreenCast SelectSources 'types' bitmask
_CURSOR_MODE_EMBEDDED = 2  # baked into the video frames, no separate track

_RESPONSE_TIMEOUT_S = 5.0  # CreateSession/SelectSources — fast, local
_START_TIMEOUT_S = 120.0  # Start() waits on the human picker — generous


def _unwrap(value: Any) -> Any:
    """Portal reply dict values arrive as dbus_next Variants (confirmed
    live: results["session_handle"] was a Variant('s', ...)); unwrap
    defensively since nested struct members may or may not already be
    unwrapped depending on dbus-next's decoding depth."""
    return value.value if hasattr(value, "value") else value


@dataclass
class ScreenCastSession:
    """One negotiated ScreenCast: a real PipeWire node ready to be opened
    by a consumer (gst-launch-1.0's pipewiresrc — see
    screen_recording_session.py)."""
    node_id: int
    pipewire_fd: int
    session_path: str
    bus: Any  # dbus_next.aio.MessageBus — kept alive for close()

    async def close(self) -> None:
        await close_session(self.bus, self.session_path)
        try:
            self.bus.disconnect()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass


def portal_available() -> bool:
    """Cheap sanity check: can dbus-next even be imported? (Confirming
    the portal interface itself is reachable would need a live bus
    round-trip — left to request_screencast_session() itself, since a
    doomed connection attempt is the same cost as a health check.)"""
    try:
        import dbus_next  # noqa: F401
        return True
    except ImportError:
        return False


async def _connect_bus():
    from dbus_next import BusType
    from dbus_next.aio import MessageBus
    return await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()


def _request_path(bus, token: str) -> str:
    """The deterministic Request object path the spec guarantees
    (verified live: matched CreateSession's actual reply exactly) — lets
    the response handler be registered BEFORE the request is sent, no
    race with a fast-resolving portal call."""
    sender = bus.unique_name[1:].replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"


def _register_response_waiter(bus, request_path: str):
    """Register the Response-signal handler BEFORE the triggering method
    call is sent — a real bug caught live: registering it AFTER
    `_portal_call()` returns races the signal, which for a fast call like
    CreateSession can (and did, in testing) already have been dispatched
    by dbus-next's read loop before the handler existed, hanging until
    timeout. Split into register-then-call-then-wait so there's no window."""
    from dbus_next import MessageType

    loop = asyncio.get_event_loop()
    fut = loop.create_future()

    def handler(msg):
        if (msg.message_type == MessageType.SIGNAL and msg.path == request_path
                and msg.interface == _REQUEST_IFACE and msg.member == "Response"):
            if not fut.done():
                fut.set_result(msg.body)
            return True
        return None

    bus.add_message_handler(handler)
    return fut, handler


async def _wait_for_response(bus, fut, handler, *, timeout: float) -> tuple[int, dict]:
    try:
        code, results = await asyncio.wait_for(fut, timeout=timeout)
    finally:
        bus.remove_message_handler(handler)
    return code, results


async def _portal_call(bus, *, member: str, signature: str, body: list):
    from dbus_next import Message
    msg = Message(destination=_BUS_NAME, path=_OBJ_PATH, interface=_SCREENCAST_IFACE,
                  member=member, signature=signature, body=body)
    return await bus.call(msg)


async def create_session(bus) -> str:
    """CreateSession -> session_handle (an object path)."""
    from dbus_next import Variant

    token = "sov" + secrets.token_hex(8)
    request_path = _request_path(bus, token)
    options = {"handle_token": Variant("s", token),
               "session_handle_token": Variant("s", token)}

    fut, handler = _register_response_waiter(bus, request_path)
    reply = await _portal_call(bus, member="CreateSession", signature="a{sv}", body=[options])
    if reply.error_name:
        bus.remove_message_handler(handler)
        raise RuntimeError(f"CreateSession failed: {reply.error_name}: {reply.body}")

    code, results = await _wait_for_response(bus, fut, handler, timeout=_RESPONSE_TIMEOUT_S)
    if code != 0:
        raise RuntimeError(f"CreateSession denied (response code {code})")
    return str(_unwrap(results["session_handle"]))


async def select_sources(bus, session_handle: str) -> None:
    """SelectSources -> nothing (raises on denial); configures the
    session to capture a monitor with the cursor baked into the frames."""
    from dbus_next import Variant

    token = "sov" + secrets.token_hex(8)
    request_path = _request_path(bus, token)
    options = {
        "types": Variant("u", _SOURCE_TYPE_MONITOR),
        "multiple": Variant("b", False),
        "cursor_mode": Variant("u", _CURSOR_MODE_EMBEDDED),
        "handle_token": Variant("s", token),
    }

    fut, handler = _register_response_waiter(bus, request_path)
    reply = await _portal_call(
        bus, member="SelectSources", signature="oa{sv}", body=[session_handle, options])
    if reply.error_name:
        bus.remove_message_handler(handler)
        raise RuntimeError(f"SelectSources failed: {reply.error_name}: {reply.body}")

    code, _results = await _wait_for_response(bus, fut, handler, timeout=_RESPONSE_TIMEOUT_S)
    if code != 0:
        raise RuntimeError(f"SelectSources denied (response code {code})")


async def start_session(bus, session_handle: str) -> int:
    """Start -> node_id of the first captured stream. UNVERIFIED live —
    this is the call that shows the OS picker dialog; nothing in this
    tool environment can click through it. First real run is Kevin's."""
    from dbus_next import Variant

    token = "sov" + secrets.token_hex(8)
    request_path = _request_path(bus, token)
    options = {"handle_token": Variant("s", token)}

    fut, handler = _register_response_waiter(bus, request_path)
    reply = await _portal_call(
        bus, member="Start", signature="osa{sv}", body=[session_handle, "", options])
    if reply.error_name:
        bus.remove_message_handler(handler)
        raise RuntimeError(f"Start failed: {reply.error_name}: {reply.body}")

    code, results = await _wait_for_response(bus, fut, handler, timeout=_START_TIMEOUT_S)
    if code == 1:
        raise RuntimeError("recording cancelled — no screen/window was picked")
    if code != 0:
        raise RuntimeError(f"Start denied (response code {code})")

    streams = _unwrap(results["streams"])
    if not streams:
        raise RuntimeError("Start succeeded but no stream was returned")
    node_id, _props = streams[0]
    return int(node_id)


async def open_pipewire_remote(bus, session_handle: str) -> int:
    """OpenPipeWireRemote -> a real fd (a direct method reply, no
    Request/Response indirection). UNVERIFIED live — needs a real
    Start()'d session first."""
    from dbus_next import Message, Variant

    msg = Message(destination=_BUS_NAME, path=_OBJ_PATH, interface=_SCREENCAST_IFACE,
                 member="OpenPipeWireRemote", signature="oa{sv}",
                 body=[session_handle, {}])
    reply = await bus.call(msg)
    if reply.error_name:
        raise RuntimeError(f"OpenPipeWireRemote failed: {reply.error_name}: {reply.body}")
    if not reply.unix_fds:
        raise RuntimeError("OpenPipeWireRemote returned no fd")
    return reply.unix_fds[0]


async def close_session(bus, session_handle: str) -> None:
    from dbus_next import Message
    msg = Message(destination=_BUS_NAME, path=session_handle,
                 interface=_SESSION_IFACE, member="Close")
    try:
        await bus.call(msg)
    except Exception:  # noqa: BLE001 — best-effort teardown, never fatal
        pass


async def request_screencast_session() -> ScreenCastSession:
    """The full negotiation, one call. Each step is its own top-level
    function so tests can monkeypatch them independently without a real
    bus connection."""
    bus = await _connect_bus()
    session_handle = await create_session(bus)
    await select_sources(bus, session_handle)
    node_id = await start_session(bus, session_handle)
    fd = await open_pipewire_remote(bus, session_handle)
    return ScreenCastSession(node_id=node_id, pipewire_fd=fd,
                             session_path=session_handle, bus=bus)
