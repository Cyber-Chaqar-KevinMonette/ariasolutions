"""Tests for game_pane.py — the ✦ godot split-pane Game Studio quick
actions. Direct Button.Pressed dispatch (not pilot.click), same reason
test_movie_pane.py/test_screen_studio_pane.py give: the pane sits past
the default test-terminal's visible width once #main.game-split is
active."""
from __future__ import annotations

import pytest
from textual.widgets import Button, Static

from sovereign_agent.game_projects import GameProject, save, set_focus


async def _open_pane(pilot):
    app = pilot.app
    btn = app.query_one("#game-pane-toggle-btn", Button)
    app.on_button_pressed(Button.Pressed(btn))
    await pilot.pause()
    return app


@pytest.mark.asyncio
async def test_toggling_reveals_game_pane():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        main = app.query_one("#main")
        assert "game-split" in main.classes
        pane = app.query_one("#game-pane", GamePane)
        header = str(pane.query_one("#game-pane-header", Static).render())
        assert "Game Studio" in header

        # toggling again hides it
        await _open_pane(pilot)
        assert "game-split" not in main.classes


@pytest.mark.asyncio
async def test_header_shows_the_focused_project_with_dimension():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane

    save(GameProject(project_name="Pane Test Game", dimension="3d"), SETTINGS.paths.data_dir)
    set_focus("pane-test-game", "testing the pane", SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#game-pane", GamePane)
        header = str(pane.query_one("#game-pane-header", Static).render())
        assert "Pane Test Game" in header
        assert "3d" in header
        assert "defining" in header  # status now shown, not just name/dimension


@pytest.mark.asyncio
async def test_busy_guard_refuses_second_click():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#game-pane", GamePane)
        assert pane._try_start("game-pane-check") is True
        assert pane._try_start("game-pane-check") is False  # busy
        pane._finish("game-pane-check")
        assert pane._try_start("game-pane-check") is True  # released


@pytest.mark.asyncio
async def test_pause_button_toggles_project_status():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane
    from sovereign_agent.game_projects import load_by_slug

    save(GameProject(project_name="Pause Test Game", dimension="2d"), SETTINGS.paths.data_dir)
    set_focus("pause-test-game", "testing pause", SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#game-pane", GamePane)
        pause_btn = pane.query_one("#game-pane-pause", Button)
        assert str(pause_btn.label) == "Pause Project"

        pane._toggle_pause()
        assert load_by_slug("pause-test-game", SETTINGS.paths.data_dir).status == "paused"
        assert str(pause_btn.label) == "Resume Project"
        status = str(pane.query_one("#game-pane-status", Static).render())
        assert "paused" in status.lower()

        pane._toggle_pause()
        assert load_by_slug("pause-test-game", SETTINGS.paths.data_dir).status == "active"
        assert str(pause_btn.label) == "Pause Project"


@pytest.mark.asyncio
async def test_pause_toggle_emits_observability_events(monkeypatch):
    """observability-gap-fix-d (quality sentinel finding, 2026-08-02):
    _toggle_pause used to be a raw local mutation with zero event
    emission, unlike every sibling action in this pane."""
    from sovereign_agent import events as events_mod
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane

    save(GameProject(project_name="Event Test Game", dimension="2d"), SETTINGS.paths.data_dir)
    set_focus("event-test-game", "testing pause events", SETTINGS.paths.data_dir)

    emitted = []
    monkeypatch.setattr(
        events_mod, "emit_event",
        lambda flag, **kw: emitted.append(flag) or "fake-event-id")

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#game-pane", GamePane)
        pane._toggle_pause()
        pane._toggle_pause()

    assert emitted == ["game-pause-d", "game-resume-d"]


@pytest.mark.asyncio
async def test_pause_without_a_focused_project_reports_clearly(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#game-pane", GamePane)
        monkeypatch.setattr(pane, "_focused_slug", lambda: None)
        pane._toggle_pause()
        status = str(pane.query_one("#game-pane-status", Static).render())
        assert "no project focused" in status


@pytest.mark.asyncio
async def test_actions_without_a_focused_project_report_clearly(monkeypatch):
    """No project focused -- every action button should say so, not
    silently no-op or crash. Monkeypatches _focused_slug directly rather
    than relying on real global focus state being empty (data_dir is
    shared/persistent across test runs, same caveat test_movie_pane.py's
    own tests document)."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.game_pane import GamePane

    async with CockpitApp().run_test() as pilot:
        app = await _open_pane(pilot)
        pane = app.query_one("#game-pane", GamePane)
        monkeypatch.setattr(pane, "_focused_slug", lambda: None)
        pane._scaffold()
        status = str(pane.query_one("#game-pane-status", Static).render())
        assert "no project focused" in status
