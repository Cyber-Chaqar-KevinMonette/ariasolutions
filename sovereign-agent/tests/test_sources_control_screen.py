"""UI smoke for the Sources Control Panel.

source-toggle-d (Kevin, 2026-07-27): "Make a control panel where I can
turn sources on and off. I want to toggle reddit off. But would like
that inside my control panel or another control panel if needed."
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_screen_lists_sources_for_the_selected_project():
    from textual.widgets import Select, Static

    from sovereign_agent.bot_projects import BotProject, save
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SourcesControlScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.discord_runtime.sources import Source, add_source

    save(BotProject(project_name="ProjA", kind="restock-alert"), SETTINGS.paths.data_dir)
    add_source(SETTINGS.paths.data_dir, "ProjA",
              Source(name="r-a", url="https://www.reddit.com/r/a/new/.rss"))
    add_source(SETTINGS.paths.data_dir, "ProjA",
              Source(name="sd-a", url="https://slickdeals.net/x.rss", enabled=False))

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_sources_control()
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
        assert app.screen.query_one("#sc-which-project", Select).value == "ProjA"
        status = str(app.screen.query_one("#sc-status", Static).render())
        assert "r-a" in status and "sd-a" in status
        assert "1/2 source(s) on" in status


@pytest.mark.asyncio
async def test_toggle_button_flips_the_selected_source():
    from textual.widgets import Button, Select

    from sovereign_agent.bot_projects import BotProject, save
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SourcesControlScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.discord_runtime.sources import Source, add_source, list_sources

    save(BotProject(project_name="ProjB", kind="restock-alert"), SETTINGS.paths.data_dir)
    add_source(SETTINGS.paths.data_dir, "ProjB",
              Source(name="feed", url="http://x", enabled=True))

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_sources_control()
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
        app.screen.query_one("#sc-which-project", Select).value = "ProjB"
        await pilot.pause()
        app.screen.query_one("#sc-which-source", Select).value = "feed"
        await pilot.pause()
        await pilot.click(app.screen.query_one("#sc-toggle-btn", Button))
        await pilot.pause()

        assert list_sources(SETTINGS.paths.data_dir, "ProjB")[0].enabled is False


@pytest.mark.asyncio
async def test_reddit_off_this_project_button_only_touches_reddit_sources():
    from textual.widgets import Button, Select

    from sovereign_agent.bot_projects import BotProject, save
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SourcesControlScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.discord_runtime.sources import Source, add_source, list_sources

    save(BotProject(project_name="ProjC", kind="restock-alert"), SETTINGS.paths.data_dir)
    add_source(SETTINGS.paths.data_dir, "ProjC",
              Source(name="r-c", url="https://www.reddit.com/r/c/new/.rss"))
    add_source(SETTINGS.paths.data_dir, "ProjC",
              Source(name="sd-c", url="https://slickdeals.net/c.rss"))

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_sources_control()
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
        app.screen.query_one("#sc-which-project", Select).value = "ProjC"
        await pilot.pause()
        await pilot.click(app.screen.query_one("#sc-reddit-off-project-btn", Button))
        await pilot.pause()

        by_name = {s.name: s for s in list_sources(SETTINGS.paths.data_dir, "ProjC")}
        assert by_name["r-c"].enabled is False
        assert by_name["sd-c"].enabled is True


@pytest.mark.asyncio
async def test_reddit_off_fleet_button_touches_every_project():
    from textual.widgets import Button

    from sovereign_agent.bot_projects import BotProject, save
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SourcesControlScreen
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.discord_runtime.sources import Source, add_source, list_sources

    save(BotProject(project_name="ProjD1", kind="restock-alert"), SETTINGS.paths.data_dir)
    save(BotProject(project_name="ProjD2", kind="restock-alert"), SETTINGS.paths.data_dir)
    add_source(SETTINGS.paths.data_dir, "ProjD1",
              Source(name="r-d1", url="https://www.reddit.com/r/d1/new/.rss"))
    add_source(SETTINGS.paths.data_dir, "ProjD2",
              Source(name="r-d2", url="https://www.reddit.com/r/d2/new/.rss"))

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_sources_control()
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
        await pilot.click(app.screen.query_one("#sc-reddit-off-fleet-btn", Button))
        await pilot.pause()

        assert list_sources(SETTINGS.paths.data_dir, "ProjD1")[0].enabled is False
        assert list_sources(SETTINGS.paths.data_dir, "ProjD2")[0].enabled is False


@pytest.mark.asyncio
async def test_action_toggles_the_screen_closed_when_reopened():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SourcesControlScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_sources_control()
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
        app.action_sources_control()
        await pilot.pause()
        assert not isinstance(app.screen, SourcesControlScreen)


@pytest.mark.asyncio
async def test_slash_command_alias_opens_the_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import SourcesControlScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app._handle_slash("/sources")
        await pilot.pause()
        assert isinstance(app.screen, SourcesControlScreen)
