"""Tests for inbox-in-chat-d.

Kevin, 2026-07-25: "my inbox should be in the chat window. Arias inbox
should also be in that chat window... How does she empty her inbox? How
do I reply to her request??" The dedicated inbox pane stays, but genuinely
NEW activity (something Aria sent, something resolved, something Kevin
left for her) now also announces as a meta-line in the main chat pane --
the collaboration record isn't a separate window Kevin has to remember
to check.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class _FakeRequest:
    request_id: str
    status: str
    direction: str
    title: str
    short_id: str = "abc123"


@pytest.mark.asyncio
async def test_first_poll_seeds_state_without_announcing_anything():
    """Nothing that already existed before the cockpit opened should
    flood chat on the very first refresh."""
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        assert app._inbox_seen_state is None
        open_items = [_FakeRequest("r1", "open", "to_human", "an existing request")]
        with patch.object(app, "_write_meta") as write_meta:
            app._announce_new_inbox_activity(open_items, [], [])

        write_meta.assert_not_called()
        assert app._inbox_seen_state == {"r1": "open"}


@pytest.mark.asyncio
async def test_new_outgoing_request_from_aria_is_announced_in_chat():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._inbox_seen_state = {}  # already seeded, nothing existed before

        new_req = _FakeRequest("r2", "open", "to_human", "found a real bug")
        with patch.object(app, "_write_meta") as write_meta:
            app._announce_new_inbox_activity([new_req], [], [])

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "found a real bug" in messages
        assert app._inbox_seen_state == {"r2": "open"}


@pytest.mark.asyncio
async def test_status_change_on_a_known_request_is_announced():
    """Kevin's actual "how do I reply" confusion -- his answer changing
    the status must be visible in chat, not just the separate pane."""
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._inbox_seen_state = {"r3": "open"}

        resolved = _FakeRequest("r3", "answered", "to_human", "should I use FOSS only?")
        with patch.object(app, "_write_meta") as write_meta:
            app._announce_new_inbox_activity([], [resolved], [])

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "should I use FOSS only?" in messages
        assert "answered" in messages


@pytest.mark.asyncio
async def test_a_new_note_kevin_left_for_aria_is_not_announced_to_kevin():
    """He obviously knows he just wrote it -- announcing his own write
    back at him would be noise, not signal."""
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._inbox_seen_state = {}

        to_aria = _FakeRequest("r4", "open", "to_aria", "please prioritize X")
        with patch.object(app, "_write_meta") as write_meta:
            app._announce_new_inbox_activity([], [], [to_aria])

        write_meta.assert_not_called()
        assert app._inbox_seen_state == {"r4": "open"}


@pytest.mark.asyncio
async def test_unchanged_state_produces_no_chat_noise():
    from sovereign_agent.cockpit import CockpitApp
    from unittest.mock import patch

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        req = _FakeRequest("r5", "open", "to_human", "steady state")
        app._inbox_seen_state = {"r5": "open"}

        with patch.object(app, "_write_meta") as write_meta:
            app._announce_new_inbox_activity([req], [], [])

        write_meta.assert_not_called()
