"""Tests for suggestions-d — the "what should I work on?" cockpit screen.

Monkeypatches work_suggestions.gather_suggestions so these never touch
real sentinel state (which is itself real, live, and slow to scan).
"""
from __future__ import annotations

import pytest


def _fake_items():
    from sovereign_agent.work_suggestions import WorkSuggestion
    return [
        WorkSuggestion(source="cache", kind="fix", summary="stale pyc files",
                       remediation="clean the pycache"),
        WorkSuggestion(source="bot-studio", kind="build",
                       summary='"Idea Bot" is defined but not built yet'),
    ]


@pytest.mark.asyncio
async def test_suggestions_button_opens_the_screen(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.suggestions_screen import SuggestionsScreen

    monkeypatch.setattr("sovereign_agent.work_suggestions.gather_suggestions",
                        lambda *a, **k: _fake_items())

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_suggestions()
        await pilot.pause()
        assert isinstance(app.screen, SuggestionsScreen)


@pytest.mark.asyncio
async def test_suggestions_are_listed(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import ListView

    monkeypatch.setattr("sovereign_agent.work_suggestions.gather_suggestions",
                        lambda *a, **k: _fake_items())

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_suggestions()
        await pilot.pause()
        lv = app.screen.query_one("#suggestions-list", ListView)
        assert len(lv.children) == 2


@pytest.mark.asyncio
async def test_empty_suggestions_shows_a_clean_message(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import ListView

    monkeypatch.setattr("sovereign_agent.work_suggestions.gather_suggestions",
                        lambda *a, **k: [])

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_suggestions()
        await pilot.pause()
        lv = app.screen.query_one("#suggestions-list", ListView)
        assert len(lv.children) == 1


@pytest.mark.asyncio
async def test_use_without_selection_warns(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Static

    monkeypatch.setattr("sovereign_agent.work_suggestions.gather_suggestions",
                        lambda *a, **k: _fake_items())

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_suggestions()
        await pilot.pause()
        await pilot.click("#suggestions-use-btn")
        await pilot.pause()
        status = app.screen.query_one("#suggestions-status", Static)
        assert "select a suggestion" in str(status.render())


@pytest.mark.asyncio
async def test_use_selected_pastes_work_command_and_closes(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.suggestions_screen import SuggestionsScreen
    from textual.widgets import Input, ListView

    monkeypatch.setattr("sovereign_agent.work_suggestions.gather_suggestions",
                        lambda *a, **k: _fake_items())

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_suggestions()
        await pilot.pause()

        lv = app.screen.query_one("#suggestions-list", ListView)
        lv.index = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        await pilot.click("#suggestions-use-btn")
        await pilot.pause()

        assert not isinstance(app.screen, SuggestionsScreen)
        input_box = app.query_one("#input-box", Input)
        assert input_box.value == "/work stale pyc files — clean the pycache"


@pytest.mark.asyncio
async def test_suggestions_command_alias_also_works(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.suggestions_screen import SuggestionsScreen

    monkeypatch.setattr("sovereign_agent.work_suggestions.gather_suggestions",
                        lambda *a, **k: _fake_items())

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app._handle_slash("/suggestions")
        await pilot.pause()
        assert isinstance(app.screen, SuggestionsScreen)
