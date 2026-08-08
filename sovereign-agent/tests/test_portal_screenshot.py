"""Tests for portal_screenshot — the single-call Screenshot portal client
used to replace grim on compositors (COSMIC) that don't implement grim's
wlr-screencopy protocol. Same fake-bus pattern as test_portal_screencast.py:
real dbus_next Message/Variant, fake bus, Response fired synchronously
inside call() to match the real portal's ordering.
"""
from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

import pytest
from dbus_next import Message, Variant

from sovereign_agent import portal_screenshot as pss


class _FakeBus:
    def __init__(self, *, reply_body, response=None):
        self.unique_name = ":1.42"
        self._handlers = []
        self._reply_body = reply_body
        self._response = response
        self.sent_messages: list[Message] = []
        self.disconnected = False

    def add_message_handler(self, handler):
        self._handlers.append(handler)

    def remove_message_handler(self, handler):
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def call(self, msg: Message) -> Message:
        msg.serial = len(self.sent_messages) + 1
        self.sent_messages.append(msg)
        if self._response is not None:
            code, results = self._response
            sig = Message.new_signal(
                path=self._pending_path, interface="org.freedesktop.portal.Request",
                member="Response", signature="ua{sv}", body=[code, results])
            for h in list(self._handlers):
                h(sig)
        return Message.new_method_return(msg, signature="o", body=self._reply_body)

    def set_pending_path(self, path):
        self._pending_path = path

    def disconnect(self):
        self.disconnected = True


def _patched_register(bus):
    real_register = pss._register_response_waiter

    def spy_register(b, request_path):
        b.set_pending_path(request_path)
        return real_register(b, request_path)

    return mock.patch.object(pss, "_register_response_waiter", side_effect=spy_register)


@pytest.mark.asyncio
async def test_capture_returns_path_from_uri():
    bus = _FakeBus(
        reply_body=["/org/freedesktop/portal/desktop/request/1_42/dummy"],
        response=(0, {"uri": Variant("s", "file:///tmp/shot.png")}),
    )
    with mock.patch.object(pss, "portal_available", return_value=True), \
         mock.patch.object(pss, "_connect_bus", return_value=bus), \
         _patched_register(bus):
        path = await pss.capture_screenshot_via_portal()

    assert path == Path("/tmp/shot.png")
    assert bus.disconnected
    call = bus.sent_messages[0]
    assert call.member == "Screenshot"
    assert call.interface == "org.freedesktop.portal.Screenshot"


@pytest.mark.asyncio
async def test_capture_returns_none_on_denial():
    bus = _FakeBus(
        reply_body=["/org/freedesktop/portal/desktop/request/1_42/dummy"],
        response=(1, {}),
    )
    with mock.patch.object(pss, "portal_available", return_value=True), \
         mock.patch.object(pss, "_connect_bus", return_value=bus), \
         _patched_register(bus):
        path = await pss.capture_screenshot_via_portal()

    assert path is None


@pytest.mark.asyncio
async def test_capture_returns_none_when_portal_unavailable():
    with mock.patch.object(pss, "portal_available", return_value=False):
        path = await pss.capture_screenshot_via_portal()

    assert path is None


@pytest.mark.asyncio
async def test_capture_returns_none_on_connect_failure():
    async def _boom():
        raise RuntimeError("no session bus")

    with mock.patch.object(pss, "portal_available", return_value=True), \
         mock.patch.object(pss, "_connect_bus", side_effect=_boom):
        path = await pss.capture_screenshot_via_portal()

    assert path is None


def test_uri_to_path_unquotes_and_strips_scheme():
    assert pss._uri_to_path("file:///tmp/a%20b.png") == Path("/tmp/a b.png")
