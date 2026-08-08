"""
test_yank_action.py — tests for action_yank_last (Ctrl+Y clipboard yank).

Strategy: run CockpitApp headlessly via app.run_test(), pre-load
_transcript, then call action_yank_last() directly and assert on
_write_clipboard() calls and the meta line written to the chat log.

We mock _write_clipboard at the instance level so no wl-copy / xclip
binary is required in CI.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(*entries: tuple[str, str]) -> list[tuple[str, str]]:
    return list(entries)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yank_copies_last_aria_block():
    """Ctrl+Y yanks lines belonging to Aria's most recent response."""
    from sovereign_agent.cockpit.app import CockpitApp

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        app._transcript = _make_transcript(
            ("you",  "hello aria"),
            ("aria", "line one of response"),
            ("aria", "line two of response"),
        )

        captured: list[str] = []

        def fake_write(text: str) -> bool:
            captured.append(text)
            return True

        with patch.object(CockpitApp, "_write_clipboard", staticmethod(fake_write)):
            app.action_yank_last()
            await pilot.pause()

        assert captured == ["line one of response\nline two of response"]


@pytest.mark.asyncio
async def test_yank_only_last_response_not_earlier():
    """When there are multiple turns, only the last Aria response is yanked."""
    from sovereign_agent.cockpit.app import CockpitApp

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        app._transcript = _make_transcript(
            ("you",  "first question"),
            ("aria", "first answer"),
            ("you",  "second question"),
            ("aria", "second answer line A"),
            ("aria", "second answer line B"),
        )

        captured: list[str] = []

        def fake_write(text: str) -> bool:
            captured.append(text)
            return True

        with patch.object(CockpitApp, "_write_clipboard", staticmethod(fake_write)):
            app.action_yank_last()
            await pilot.pause()

        assert captured == ["second answer line A\nsecond answer line B"]


@pytest.mark.asyncio
async def test_yank_with_no_transcript_shows_meta():
    """If transcript is empty, a friendly meta message appears in the log."""
    from sovereign_agent.cockpit.app import CockpitApp

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        app._transcript = []
        chat = app.query_one("#chat-log")
        lines_before = len(chat.lines)

        with patch.object(CockpitApp, "_write_clipboard", staticmethod(lambda t: True)):
            app.action_yank_last()
            await pilot.pause()

        # A meta line must have been written (the "nothing to yank" notice)
        assert len(chat.lines) > lines_before


@pytest.mark.asyncio
async def test_yank_with_no_aria_after_last_you_shows_meta():
    """If the last message was from 'you' with no Aria follow-up, show a notice."""
    from sovereign_agent.cockpit.app import CockpitApp

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        app._transcript = _make_transcript(
            ("you",  "a question with no answer yet"),
        )
        chat = app.query_one("#chat-log")
        lines_before = len(chat.lines)

        clipboard_calls: list[str] = []

        def fake_write(text: str) -> bool:
            clipboard_calls.append(text)
            return True

        with patch.object(CockpitApp, "_write_clipboard", staticmethod(fake_write)):
            app.action_yank_last()
            await pilot.pause()

        # Clipboard must NOT have been called — nothing to copy
        assert clipboard_calls == []
        # But a meta notice must appear in the chat
        assert len(chat.lines) > lines_before


@pytest.mark.asyncio
async def test_yank_failure_shows_warning():
    """When _write_clipboard returns False, a yellow warning appears."""
    from sovereign_agent.cockpit.app import CockpitApp

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        app._transcript = _make_transcript(
            ("you",  "ping"),
            ("aria", "pong"),
        )
        chat = app.query_one("#chat-log")
        lines_before = len(chat.lines)

        with patch.object(CockpitApp, "_write_clipboard", staticmethod(lambda t: False)):
            app.action_yank_last()
            await pilot.pause()

        # A warning line should appear
        assert len(chat.lines) > lines_before


@pytest.mark.asyncio
async def test_yank_binding_exists():
    """ctrl+y must appear in CockpitApp.BINDINGS."""
    from sovereign_agent.cockpit.app import CockpitApp

    keys = {b.key for b in CockpitApp.BINDINGS}
    assert "ctrl+y" in keys, f"ctrl+y not found in BINDINGS — got: {keys}"


@pytest.mark.asyncio
async def test_yank_aria_only_session_no_you():
    """If transcript has aria lines but no 'you' entry, all aria lines are yanked."""
    from sovereign_agent.cockpit.app import CockpitApp

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # Simulate a session where meta/aria wrote before any 'you' entry
        app._transcript = _make_transcript(
            ("aria", "welcome message line 1"),
            ("aria", "welcome message line 2"),
        )

        captured: list[str] = []

        def fake_write(text: str) -> bool:
            captured.append(text)
            return True

        with patch.object(CockpitApp, "_write_clipboard", staticmethod(fake_write)):
            app.action_yank_last()
            await pilot.pause()

        assert captured == ["welcome message line 1\nwelcome message line 2"]
