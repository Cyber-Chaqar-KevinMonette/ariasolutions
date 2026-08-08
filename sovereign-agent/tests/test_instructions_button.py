"""Tests for instructions-d — the ? help button.

Kevin, 2026-07-25: "add a instructions button next to the new discord
button for how to use the system and interface, and for what kind of
task, work, and workflows." Reuses the existing F1 HelpScreen (which
already covers the interface + points at /workflows for task/workflow
guidance) rather than building a second, competing reference.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_instructions_button_opens_the_help_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import HelpScreen

    # header-reorg-d (2026-08-02): instructions-btn was removed from the
    # header row entirely — action_instructions() already just opens the
    # same HelpScreen the ⋮ popup's "help" entry opens, so no popup entry
    # was needed either. Call the (unchanged) action directly.
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_instructions()
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_instructions_command_opens_the_help_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import HelpScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app._handle_slash("/instructions")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_instructions_button_toggles_closed_on_second_press():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import HelpScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_instructions()
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        app.action_instructions()
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


def test_help_text_still_points_at_the_workflows_catalog():
    """The instructions button intentionally reuses this screen instead of
    duplicating content — confirm the "what kind of task/workflows"
    answer is actually still in it."""
    import inspect
    from sovereign_agent.cockpit import app as app_module
    source = inspect.getsource(app_module.HelpScreen.compose)
    assert "/workflows" in source
    assert "workflows catalog" in source
