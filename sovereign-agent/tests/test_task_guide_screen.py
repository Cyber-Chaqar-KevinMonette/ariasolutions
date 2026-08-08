"""Tests for task-guide-d — the "everything you can do with her" cockpit screen.

Kevin, 2026-07-26: "Create a task guide button on the frontend so I can
see everything I can do with her and so I can test everything following
the guide."
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_task_guide_button_opens_the_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.task_guide_screen import TaskGuideScreen

    # header-reorg-d (2026-08-02): moved off the header row into the ⋮
    # commands popup (action="task-guide") — action_task_guide() unchanged.
    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_task_guide()
        await pilot.pause()
        assert isinstance(app.screen, TaskGuideScreen)


@pytest.mark.asyncio
async def test_task_guide_button_toggles_closed_on_second_click():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.task_guide_screen import TaskGuideScreen

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_task_guide()
        await pilot.pause()
        assert isinstance(app.screen, TaskGuideScreen)
        app.action_task_guide()
        await pilot.pause()
        assert not isinstance(app.screen, TaskGuideScreen)


@pytest.mark.asyncio
async def test_task_guide_command_alias_also_works():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.task_guide_screen import TaskGuideScreen

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app._handle_slash("/task-guide")
        await pilot.pause()
        assert isinstance(app.screen, TaskGuideScreen)


@pytest.mark.asyncio
async def test_escape_closes_the_task_guide():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test(size=(240, 50)) as pilot:
        app = pilot.app
        app.action_task_guide()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from textual.screen import Screen
        assert type(app.screen) is Screen


def test_render_guide_text_includes_every_category_and_a_real_total():
    from sovereign_agent.cockpit.task_guide_screen import render_guide_text
    from sovereign_agent.task_guide import CATEGORIES, total_tool_count

    text = render_guide_text()
    for cat in CATEGORIES:
        assert cat.title in text
        for entry in cat.entries:
            assert entry.label in text
            assert entry.example in text
    assert str(total_tool_count()) in text


def test_render_guide_text_never_raises_even_if_total_tool_count_breaks(monkeypatch):
    import sovereign_agent.task_guide as tg
    monkeypatch.setattr(tg, "total_tool_count", lambda: (_ for _ in ()).throw(RuntimeError))
    from sovereign_agent.cockpit.task_guide_screen import render_guide_text
    text = render_guide_text()  # must not raise
    assert "Task Guide" in text
