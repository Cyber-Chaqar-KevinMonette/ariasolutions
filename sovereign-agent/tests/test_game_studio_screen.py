"""Tests for game-studio-d — the Game Studio cockpit screen (real Textual
pilot click-through, mirrors test_bot_projects.py's own UI smoke pattern)."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import GameProject, load, save


@pytest.mark.asyncio
async def test_game_studio_opens_and_saves():
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import GameStudioScreen
    from sovereign_agent.config import SETTINGS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_game_studio()
        await pilot.pause()
        assert isinstance(app.screen, GameStudioScreen)
        app.screen.query_one("#game-project-name", Input).value = "SmokeGame"
        app.screen.query_one("#game-concept", Input).value = "a test concept"
        await pilot.click(app.screen.query_one("#game-save-btn", Button))
        await pilot.pause()
        saved = load("SmokeGame", SETTINGS.paths.data_dir)
        assert saved is not None and saved.concept == "a test concept"


@pytest.mark.asyncio
async def test_game_studio_browse_carousel():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import GameStudioScreen
    from sovereign_agent.config import SETTINGS

    save(GameProject(project_name="One", genre="puzzle"), SETTINGS.paths.data_dir)
    save(GameProject(project_name="Two", genre="platformer"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_game_studio()
        await pilot.pause()
        assert isinstance(app.screen, GameStudioScreen)
        assert app.screen._pi == 0
        nxt = app.screen.query_one("#game-next", Button)
        nxt.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(nxt)
        await pilot.pause()
        assert app.screen._pi == 1


@pytest.mark.asyncio
async def test_set_focus_without_reason_is_refused():
    from textual.widgets import Button, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import GameStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.game_projects import get_focus

    save(GameProject(project_name="NoReasonGame"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_game_studio()
        await pilot.pause()
        assert isinstance(app.screen, GameStudioScreen)
        btn = app.screen.query_one("#game-set-focus", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        assert get_focus(SETTINGS.paths.data_dir).slug is None
        assert "reason" in str(app.screen.query_one("#game-help", Static).render())


@pytest.mark.asyncio
async def test_set_focus_with_reason_succeeds():
    from textual.widgets import Button, Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import GameStudioScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.game_projects import get_focus, slugify

    save(GameProject(project_name="FocusGame"), SETTINGS.paths.data_dir)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_game_studio()
        await pilot.pause()
        assert isinstance(app.screen, GameStudioScreen)
        app.screen.query_one("#game-focus-reason", Input).value = "operator asked to start here"
        btn = app.screen.query_one("#game-set-focus", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        focus = get_focus(SETTINGS.paths.data_dir)
        assert focus.slug == slugify("FocusGame")
