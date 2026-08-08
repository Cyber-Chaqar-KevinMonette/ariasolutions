"""Tests for owner-bridge-remote-d — messaging/controlling Aria from
Discord (#owner-bridge, owner-only, already private by the blueprint's
own build).

Kevin, 2026-07-25: "I want to be able to message her from discord and
start sessions with her and work sessions and auto work sessions etc..
Maybe add additional hours and all the above." Every command here is a
SECOND entry point into functions the cockpit's own slash commands
already call (session_bridge.start_goal_session, arm_custom_hours,
AutoCrownStore) — nothing bypasses a safety gate that exists elsewhere.
"""
from __future__ import annotations

import asyncio

import pytest

from sovereign_agent.discord_admin.bot import handle_owner_bridge_message


class _Sender:
    """Collects every `send(text)` call; awaitable, matches
    discord.TextChannel.send's shape."""
    def __init__(self):
        self.sent: list[str] = []

    async def __call__(self, text: str) -> None:
        self.sent.append(text)


@pytest.mark.asyncio
async def test_empty_content_is_a_pure_noop():
    send = _Sender()
    await handle_owner_bridge_message("", send)
    assert send.sent == []


@pytest.mark.asyncio
async def test_plain_message_queues_via_the_existing_operator_queue(monkeypatch):
    from sovereign_agent import session_bridge
    queued = []
    monkeypatch.setattr(session_bridge, "queue_operator_message",
                        lambda text: queued.append(text) or "req-1")

    send = _Sender()
    await handle_owner_bridge_message("check on the shop stats please", send)

    assert queued == ["check on the shop stats please"]
    assert "queued" in send.sent[0].lower()


@pytest.mark.asyncio
async def test_work_command_starts_a_session_in_the_background(monkeypatch):
    from sovereign_agent import session_bridge
    started = []

    class _FakeResult:
        status = "completed"

    async def fake_start(goal):
        started.append(goal)
        return _FakeResult()

    monkeypatch.setattr(session_bridge, "start_goal_session", fake_start)

    send = _Sender()
    await handle_owner_bridge_message("!work clean up the inbox", send)
    assert "starting" in send.sent[0].lower()
    assert "clean up the inbox" in send.sent[0]

    await asyncio.sleep(0)  # let the fire-and-forget task run
    await asyncio.sleep(0)
    assert started == ["clean up the inbox"]
    assert any("session finished" in s for s in send.sent)


@pytest.mark.asyncio
async def test_work_command_without_a_goal_shows_usage():
    send = _Sender()
    await handle_owner_bridge_message("!work", send)
    assert "usage: !work" in send.sent[0]


@pytest.mark.asyncio
async def test_work_session_failure_is_reported_not_swallowed(monkeypatch):
    from sovereign_agent import session_bridge

    async def fake_start(goal):
        raise RuntimeError("budget exceeded")

    monkeypatch.setattr(session_bridge, "start_goal_session", fake_start)

    send = _Sender()
    await handle_owner_bridge_message("!work do something", send)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert any("session failed" in s and "RuntimeError" in s for s in send.sent)


@pytest.mark.asyncio
async def test_auto_command_arms_via_the_existing_tier_gated_function(monkeypatch):
    from sovereign_agent.modes_crown import profiles as mc

    class _FakeProfile:
        description = "Work + a 3-hour lease, picked directly."

    monkeypatch.setattr(mc, "arm_custom_hours", lambda hours: _FakeProfile())

    send = _Sender()
    await handle_owner_bridge_message("!auto 3", send)
    assert "auto armed" in send.sent[0]


@pytest.mark.asyncio
async def test_auto_command_reports_a_tier_refusal_honestly(monkeypatch):
    from sovereign_agent.modes_crown import profiles as mc

    def _refuse(hours):
        raise mc.CrownError("Trust tier 3 exceeds max allowed (1)")

    monkeypatch.setattr(mc, "arm_custom_hours", _refuse)

    send = _Sender()
    await handle_owner_bridge_message("!auto 5", send)
    assert "auto arm failed" in send.sent[0]
    assert "exceeds max allowed" in send.sent[0]


@pytest.mark.asyncio
async def test_auto_command_rejects_bad_input():
    send = _Sender()
    await handle_owner_bridge_message("!auto banana", send)
    assert "usage: !auto" in send.sent[0]


@pytest.mark.asyncio
async def test_addtime_command_extends_an_armed_session(monkeypatch):
    from sovereign_agent import auto_crown

    class _FakeSession:
        def remaining_minutes(self):
            return 125.0

    class _FakeStore:
        def extend(self, hours):
            return _FakeSession()

        def extend_trust_tier(self, hours):
            return True

    monkeypatch.setattr(auto_crown, "get_auto_crown_store", lambda: _FakeStore())

    send = _Sender()
    await handle_owner_bridge_message("!addtime 1", send)
    assert "+1h added" in send.sent[0]
    assert "2h05m remaining" in send.sent[0]
    assert "elevated tier extended too" in send.sent[0]


@pytest.mark.asyncio
async def test_addtime_with_nothing_armed_gives_a_clear_message(monkeypatch):
    from sovereign_agent import auto_crown

    class _FakeStore:
        def extend(self, hours):
            raise ValueError("no active auto session to extend")

    monkeypatch.setattr(auto_crown, "get_auto_crown_store", lambda: _FakeStore())

    send = _Sender()
    await handle_owner_bridge_message("!addtime", send)
    assert "arm one first" in send.sent[0]


@pytest.mark.asyncio
async def test_status_command_reports_active_auto(monkeypatch):
    from sovereign_agent import auto_crown

    class _FakeStatus:
        status = "active"
        trust_tier = 3

        def remaining_minutes(self):
            return 90.0

    class _FakeStore:
        def status(self):
            return _FakeStatus()

    monkeypatch.setattr(auto_crown, "get_auto_crown_store", lambda: _FakeStore())

    send = _Sender()
    await handle_owner_bridge_message("!status", send)
    assert "AUTO active" in send.sent[0]
    assert "1h30m" in send.sent[0]
    assert "T3" in send.sent[0]


@pytest.mark.asyncio
async def test_status_command_reports_semi_auto_when_nothing_armed(monkeypatch):
    from sovereign_agent import auto_crown

    class _FakeStore:
        def status(self):
            return None

    monkeypatch.setattr(auto_crown, "get_auto_crown_store", lambda: _FakeStore())

    send = _Sender()
    await handle_owner_bridge_message("!status", send)
    assert "Semi-Auto" in send.sent[0]


@pytest.mark.asyncio
async def test_audit_log_is_written_when_a_path_is_given(tmp_path, monkeypatch):
    from sovereign_agent import session_bridge
    monkeypatch.setattr(session_bridge, "queue_operator_message", lambda text: "req-1")

    audit_path = tmp_path / "audit.jsonl"
    send = _Sender()
    await handle_owner_bridge_message("hello there", send, audit_path=audit_path)

    assert audit_path.is_file()
    import json
    lines = [json.loads(l) for l in audit_path.read_text().splitlines()]
    assert lines[0]["op"] == "owner-bridge-message"
