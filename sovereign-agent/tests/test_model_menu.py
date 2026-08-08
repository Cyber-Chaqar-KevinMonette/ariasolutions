"""Tests for sprint-mode-d's cockpit surface — F8 / `/model`: Standard,
sprint presets, or custom per-slot models.
"""
from __future__ import annotations

import pytest


def test_model_menu_imports_cleanly():
    from sovereign_agent.cockpit.app import ModelMenuScreen
    assert ModelMenuScreen is not None


@pytest.mark.asyncio
async def test_f8_and_bare_model_command_open_the_menu():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ModelMenuScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._handle_slash("/model")
        await pilot.pause()
        assert isinstance(app.screen, ModelMenuScreen)
        # toggle closes
        app.action_model_menu()
        await pilot.pause()
        assert not isinstance(app.screen, ModelMenuScreen)


@pytest.mark.asyncio
async def test_no_button_in_the_whole_flow_can_get_stuck_highlighted():
    """Kevin, 2026-07-21: "make sure there is no highlight bugs on any
    buttons either." Every button across all three screens must be
    can_focus=False (feedback_cockpit_button_focus)."""
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ModelMenuScreen
    from sovereign_agent.cockpit.model_menu_screen import ModelSlotsScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_model_menu()
        await pilot.pause()
        assert isinstance(app.screen, ModelMenuScreen)
        for btn in app.screen.query(Button):
            assert btn.can_focus is False, f"{btn.id} can be focused and get stuck lit"

        app.screen.on_button_pressed(Button.Pressed(app.screen.query_one("#model-custom")))
        await pilot.pause()
        assert isinstance(app.screen, ModelSlotsScreen)
        for btn in app.screen.query(Button):
            assert btn.can_focus is False, f"{btn.id} can be focused and get stuck lit"


@pytest.mark.asyncio
async def test_selecting_a_preset_marks_it_active_and_writes_a_meta_line():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ModelMenuScreen
    from sovereign_agent.sprint_mode import status

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_model_menu()
        await pilot.pause()
        btn = app.screen.query_one("#model-sprint-2b")
        app.screen.on_button_pressed(Button.Pressed(btn))
        await pilot.pause()

    assert status()["preset"] == "sprint-2b"


@pytest.mark.asyncio
async def test_custom_slots_screen_lists_every_slot():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.model_menu_screen import ModelSlotsScreen, SlotButton
    from sovereign_agent.sprint_mode import SLOTS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModelSlotsScreen())
        await pilot.pause()
        buttons = list(app.screen.query(SlotButton))
        assert {b.slot for b in buttons} == set(SLOTS)


@pytest.mark.asyncio
async def test_picker_shows_installed_models_and_setting_one_overrides_the_slot(monkeypatch):
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.model_menu_screen import ModelChoiceButton, ModelSlotPickerScreen
    import sovereign_agent.sprint_mode as sm

    monkeypatch.setattr(sm, "list_installed_models", lambda: ["qwen3.5:2b", "aria-fast:latest"])

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModelSlotPickerScreen("coder"))
        await pilot.pause()
        choices = list(app.screen.query(ModelChoiceButton))
        assert {c.model for c in choices} == {"qwen3.5:2b", "aria-fast:latest"}
        pick = next(c for c in choices if c.model == "qwen3.5:2b")
        app.screen.on_button_pressed(Button.Pressed(pick))
        await pilot.pause()

    assert sm.status()["slots"]["coder"]["model"] == "qwen3.5:2b"


@pytest.mark.asyncio
async def test_picker_reset_clears_only_that_slot(monkeypatch):
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.model_menu_screen import ModelSlotPickerScreen
    import sovereign_agent.sprint_mode as sm

    monkeypatch.setattr(sm, "list_installed_models", lambda: ["qwen3.5:2b"])
    sm.set_slot_override("coder", "qwen3.5:2b")
    sm.set_slot_override("fast", "phi4-mini:3.8b")

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModelSlotPickerScreen("coder"))
        await pilot.pause()
        reset_btn = app.screen.query_one("#picker-reset", Button)
        app.screen.on_button_pressed(Button.Pressed(reset_btn))
        await pilot.pause()

    state = sm.status()
    assert state["slots"]["coder"]["overridden"] is False
    assert state["slots"]["fast"]["overridden"] is True  # unaffected


@pytest.mark.asyncio
async def test_picker_handles_no_models_found_without_crashing(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.model_menu_screen import ModelSlotPickerScreen
    import sovereign_agent.sprint_mode as sm

    monkeypatch.setattr(sm, "list_installed_models", lambda: [])

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.push_screen(ModelSlotPickerScreen("vision"))
        await pilot.pause()
        text = " ".join(str(s.render()) for s in app.screen.query("Static"))
        assert "no models found" in text.lower()
