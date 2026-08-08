"""Behavior tests for aria-flexi-layout, promoted to live tests/ — tests
the REAL, already-patched cockpit. Plain imports, no shadow copy.
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_boots_in_layout_a_by_default():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        main = pilot.app.query_one("#main")
        assert not main.has_class("layout-rows")
        # all five panes still present and mounted
        for pane in ("#chat-pane", "#memory-pane", "#live-pane",
                     "#inbox-pane", "#atelier-pane"):
            assert pilot.app.query_one(pane) is not None


@pytest.mark.asyncio
async def test_toggle_switches_to_rows_and_back():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_toggle_layout()
        await pilot.pause()
        assert app.query_one("#main").has_class("layout-rows")
        # panes render in the grid without exploding
        for pane in ("#chat-pane", "#memory-pane", "#live-pane",
                     "#inbox-pane", "#atelier-pane"):
            assert app.query_one(pane).size.width > 0
        app.action_toggle_layout()
        await pilot.pause()
        assert not app.query_one("#main").has_class("layout-rows")


@pytest.mark.asyncio
async def test_preference_persists_and_is_honored_on_next_boot():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        pilot.app.action_toggle_layout()
        await pilot.pause()
    pref_path = SETTINGS.paths.config_dir / "cockpit_layout.json"
    assert pref_path.exists()
    assert json.loads(pref_path.read_text())["layout"] == "rows"

    # A fresh boot honors the saved preference.
    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        assert pilot.app.query_one("#main").has_class("layout-rows")


@pytest.mark.asyncio
async def test_keybinding_registered():
    from sovereign_agent.cockpit import CockpitApp

    bindings = {b.key: b.action for b in CockpitApp.BINDINGS}
    assert bindings.get("ctrl+o") == "toggle_layout"
