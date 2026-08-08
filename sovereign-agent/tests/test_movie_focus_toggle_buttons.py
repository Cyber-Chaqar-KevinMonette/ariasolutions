"""Tests for movie-focus-d — the header '✦ movie' and '▪ bots' buttons.

Kevin, 2026-07-28: "add a movie studio button next to the game button and
a pause all bots button next to the movie button" — direct one-click
access for GPU-heavy movie work, instead of typing /movies or /bots off.

The header row now has enough buttons that the new ones sit past the
default test-terminal's visible width, so pilot.click(...) throws
OutOfBounds on pixel geometry alone. Dispatching Button.Pressed directly
(same idiom test_capability_test_cockpit.py uses for Input.Submitted)
proves the wiring without fighting terminal geometry.
"""
from __future__ import annotations

import pytest
from textual.widgets import Button


@pytest.mark.asyncio
async def test_movie_toggle_button_shows_and_hides_the_split_pane():
    """movie-focus-d reshaped this button's behavior: it now toggles the
    persistent #movie-pane split (CSS class on #main), NOT the modal —
    same "pure CSS, widget tree untouched" pattern obs-focus/layout-rows
    already use for #chat-pane."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        main = app.query_one("#main")
        assert "movie-split" not in main.classes
        assert not isinstance(app.screen, MovieStudioScreen)   # never opens the modal

        btn = app.query_one("#movie-toggle-btn", Button)
        app.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "movie-split" in main.classes
        assert not isinstance(app.screen, MovieStudioScreen)

        app.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert "movie-split" not in main.classes


@pytest.mark.asyncio
async def test_movies_slash_command_still_opens_the_full_modal_unchanged():
    """Two doors, no regression: /movies (typed) keeps opening the full
    editing modal exactly as before movie-focus-d, independent of the new
    header button's changed behavior."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import MovieStudioScreen
    from textual.widgets import Input

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/movies", validation_result=None))
        await pilot.pause()
        assert isinstance(app.screen, MovieStudioScreen)


@pytest.mark.asyncio
async def test_bots_toggle_button_stops_bots_when_any_are_active(monkeypatch):
    from sovereign_agent import bot_services
    from sovereign_agent.cockpit import CockpitApp

    calls: list[bool] = []
    monkeypatch.setattr(
        bot_services, "service_states",
        lambda runner=None: {"aria-bot.service": {"active": True, "state": "active", "pid": 1},
                              "aria-duty.service": {"active": False, "state": "inactive", "pid": 0}},
    )

    def _fake_toggle(on, *, runner=None, data_dir=None):
        calls.append(on)
        return "▪ Discord bots STOPPED — aria-bot ▪ · aria-duty ▪"

    monkeypatch.setattr(bot_services, "toggle", _fake_toggle)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        btn = app.query_one("#bots-toggle-btn", Button)
        app.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert calls == [False]   # any unit active -> stop both


@pytest.mark.asyncio
async def test_bots_toggle_button_starts_bots_when_none_are_active(monkeypatch):
    from sovereign_agent import bot_services
    from sovereign_agent.cockpit import CockpitApp

    calls: list[bool] = []
    monkeypatch.setattr(
        bot_services, "service_states",
        lambda runner=None: {"aria-bot.service": {"active": False, "state": "inactive", "pid": 0},
                              "aria-duty.service": {"active": False, "state": "inactive", "pid": 0}},
    )

    def _fake_toggle(on, *, runner=None, data_dir=None):
        calls.append(on)
        return "◉ Discord bots STARTED — aria-bot ◉ · aria-duty ◉"

    monkeypatch.setattr(bot_services, "toggle", _fake_toggle)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        btn = app.query_one("#bots-toggle-btn", Button)
        app.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        assert calls == [True]   # nothing active -> start both


@pytest.mark.asyncio
async def test_bots_toggle_button_failure_reports_honestly_not_crash(monkeypatch):
    from sovereign_agent import bot_services
    from sovereign_agent.cockpit import CockpitApp

    def _raise(*a, **kw):
        raise RuntimeError("systemctl unavailable")

    monkeypatch.setattr(bot_services, "service_states", _raise)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        btn = app.query_one("#bots-toggle-btn", Button)
        app.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()
        # never crashes the app — degrades to an honest message instead
        assert app.is_running
