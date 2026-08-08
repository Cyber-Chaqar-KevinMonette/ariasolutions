"""Tests for portal_screencast — the ScreenCast portal client.

Real dbus_next Message/Variant classes are used (a real installed
dependency), but the bus itself is faked — no real D-Bus connection. The
fake bus fires the Response signal SYNCHRONOUSLY inside call(), before
returning the method reply — this is deliberate: it's the exact race
that a live test caught for real (registering the response handler AFTER
the triggering call had already returned missed a fast portal's signal
entirely and hung until timeout). If that ordering regresses, these
tests deadlock/timeout instead of silently passing.
"""
from __future__ import annotations

import asyncio

import pytest
from dbus_next import Message, MessageType, Variant

from sovereign_agent import portal_screencast as ps


class _FakeBus:
    """Replies to every call() with a method-return carrying `reply_body`,
    then synchronously fires a Response signal (if `response` is set) to
    every currently-registered handler, matching whatever the request's
    own object path is (dbus-next computes it deterministically from
    unique_name + handle_token, same as the real portal)."""

    def __init__(self, *, reply_body, reply_signature="o",
                response=None, unix_fds=None):
        self.unique_name = ":1.42"
        self._handlers = []
        self._reply_body = reply_body
        self._reply_signature = reply_signature
        self._response = response
        self._unix_fds = unix_fds or []
        self.sent_messages: list[Message] = []

    def add_message_handler(self, handler):
        self._handlers.append(handler)

    def remove_message_handler(self, handler):
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def call(self, msg: Message) -> Message:
        # A real MessageBus assigns a real serial before sending; ours
        # doesn't send anything, so fake it — new_method_return() requires
        # a truthy reply_serial.
        msg.serial = len(self.sent_messages) + 1
        self.sent_messages.append(msg)
        if self._response is not None:
            code, results = self._response
            sig = Message.new_signal(
                path=self._pending_path, interface="org.freedesktop.portal.Request",
                member="Response", signature="ua{sv}", body=[code, results])
            for h in list(self._handlers):
                h(sig)
        return Message.new_method_return(
            msg, signature=self._reply_signature, body=self._reply_body,
            unix_fds=self._unix_fds)

    def set_pending_path(self, path):
        self._pending_path = path


def test_request_path_matches_live_verified_formula():
    bus = _FakeBus(reply_body=["x"])
    path = ps._request_path(bus, "TOKEN123")
    assert path == "/org/freedesktop/portal/desktop/request/1_42/TOKEN123"


def test_unwrap_handles_variant_and_plain_values():
    assert ps._unwrap(Variant("s", "hello")) == "hello"
    assert ps._unwrap("already-plain") == "already-plain"


@pytest.mark.asyncio
async def test_create_session_returns_session_handle():
    bus = _FakeBus(reply_body=["/org/freedesktop/portal/desktop/request/1_42/dummy"])

    # Patch secrets.token_hex is unnecessary — instead intercept the real
    # request path the module computes (deterministic from unique_name +
    # its own freshly-generated token) by wiring the fake bus AFTER the
    # module tells us what path it registered against.
    real_register = ps._register_response_waiter

    def spy_register(b, request_path):
        b.set_pending_path(request_path)
        return real_register(b, request_path)

    bus._response = (0, {"session_handle": Variant("s", "/org/.../session/x")})
    import unittest.mock as mock
    with mock.patch.object(ps, "_register_response_waiter", side_effect=spy_register):
        session_handle = await ps.create_session(bus)

    assert session_handle == "/org/.../session/x"
    call = bus.sent_messages[0]
    assert call.member == "CreateSession"
    assert call.interface == "org.freedesktop.portal.ScreenCast"


@pytest.mark.asyncio
async def test_create_session_raises_on_denial():
    bus = _FakeBus(reply_body=["/org/freedesktop/portal/desktop/request/1_42/dummy"],
                   response=(1, {}))
    real_register = ps._register_response_waiter

    def spy_register(b, request_path):
        b.set_pending_path(request_path)
        return real_register(b, request_path)

    import unittest.mock as mock
    with mock.patch.object(ps, "_register_response_waiter", side_effect=spy_register):
        with pytest.raises(RuntimeError, match="denied"):
            await ps.create_session(bus)


@pytest.mark.asyncio
async def test_start_session_returns_first_stream_node_id():
    bus = _FakeBus(reply_body=["/org/freedesktop/portal/desktop/request/1_42/dummy"])
    bus._response = (0, {"streams": Variant("a(ua{sv})", [[42, {}], [99, {}]])})
    real_register = ps._register_response_waiter

    def spy_register(b, request_path):
        b.set_pending_path(request_path)
        return real_register(b, request_path)

    import unittest.mock as mock
    with mock.patch.object(ps, "_register_response_waiter", side_effect=spy_register):
        node_id = await ps.start_session(bus, "/org/.../session/x")

    assert node_id == 42


@pytest.mark.asyncio
async def test_start_session_raises_on_cancel():
    bus = _FakeBus(reply_body=["/org/freedesktop/portal/desktop/request/1_42/dummy"],
                   response=(1, {}))
    real_register = ps._register_response_waiter

    def spy_register(b, request_path):
        b.set_pending_path(request_path)
        return real_register(b, request_path)

    import unittest.mock as mock
    with mock.patch.object(ps, "_register_response_waiter", side_effect=spy_register):
        with pytest.raises(RuntimeError, match="cancelled"):
            await ps.start_session(bus, "/org/.../session/x")


@pytest.mark.asyncio
async def test_open_pipewire_remote_returns_fd():
    bus = _FakeBus(reply_body=[], reply_signature="h", unix_fds=[17])
    fd = await ps.open_pipewire_remote(bus, "/org/.../session/x")
    assert fd == 17


@pytest.mark.asyncio
async def test_open_pipewire_remote_raises_without_fd():
    bus = _FakeBus(reply_body=[], reply_signature="h", unix_fds=[])
    with pytest.raises(RuntimeError, match="no fd"):
        await ps.open_pipewire_remote(bus, "/org/.../session/x")


@pytest.mark.asyncio
async def test_request_screencast_session_orchestrates_all_steps(monkeypatch):
    """No real bus at all — every step function is monkeypatched, proving
    request_screencast_session() calls them in the right order and wires
    the result into a ScreenCastSession."""
    calls = []

    async def fake_connect_bus():
        return "FAKE_BUS"

    async def fake_create_session(bus):
        calls.append(("create_session", bus))
        return "SESSION_HANDLE"

    async def fake_select_sources(bus, session_handle):
        calls.append(("select_sources", bus, session_handle))

    async def fake_start_session(bus, session_handle):
        calls.append(("start_session", bus, session_handle))
        return 7

    async def fake_open_pipewire_remote(bus, session_handle):
        calls.append(("open_pipewire_remote", bus, session_handle))
        return 99

    monkeypatch.setattr(ps, "_connect_bus", fake_connect_bus)
    monkeypatch.setattr(ps, "create_session", fake_create_session)
    monkeypatch.setattr(ps, "select_sources", fake_select_sources)
    monkeypatch.setattr(ps, "start_session", fake_start_session)
    monkeypatch.setattr(ps, "open_pipewire_remote", fake_open_pipewire_remote)

    session = await ps.request_screencast_session()

    assert [c[0] for c in calls] == [
        "create_session", "select_sources", "start_session", "open_pipewire_remote"]
    assert session.node_id == 7
    assert session.pipewire_fd == 99
    assert session.session_path == "SESSION_HANDLE"
    assert session.bus == "FAKE_BUS"


@pytest.mark.asyncio
async def test_screencast_session_close_calls_close_session_and_disconnects(monkeypatch):
    closed = []

    async def fake_close_session(bus, session_handle):
        closed.append((bus, session_handle))

    class _DisconnectableBus:
        def __init__(self):
            self.disconnected = False

        def disconnect(self):
            self.disconnected = True

    monkeypatch.setattr(ps, "close_session", fake_close_session)
    bus = _DisconnectableBus()
    session = ps.ScreenCastSession(node_id=1, pipewire_fd=2, session_path="X", bus=bus)

    await session.close()

    assert closed == [(bus, "X")]
    assert bus.disconnected is True


def test_portal_available_true_when_dbus_next_importable():
    assert ps.portal_available() is True
