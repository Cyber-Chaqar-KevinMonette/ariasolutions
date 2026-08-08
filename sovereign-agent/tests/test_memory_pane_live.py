"""Tests for memory-pane-live-d.

Kevin, 2026-07-25: "the memory window shows that the metrics barely move
up as she completes task." Root cause: _notify_memory_changed() existed
but nothing ever called it -- the pane only ever refreshed on a 15s timer.
Fixed by reacting to the same tool-start-d events the events pane already
tails (memory-write tools have no handle back to the app to call it
directly), plus dropping the timer floor to 5s to match other strips.
"""
from __future__ import annotations

import json

import pytest


def test_memory_write_tools_cover_the_real_write_tools():
    from sovereign_agent.cockpit.app import _MEMORY_WRITE_TOOLS

    assert "memory_write" in _MEMORY_WRITE_TOOLS
    assert "write_behavior_pattern" in _MEMORY_WRITE_TOOLS
    assert "write_honor_note" in _MEMORY_WRITE_TOOLS


@pytest.mark.asyncio
async def test_memory_write_tool_event_schedules_a_pane_refresh():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        calls = []
        app._notify_memory_changed = lambda: calls.append(True)

        raw = json.dumps({
            "ts": "2026-07-25T00:00:00Z", "flag": "tool-start-d",
            "payload": {"tool": "memory_write", "tier": 1},
        })
        app._render_event(raw)
        await pilot.pause(1.2)  # the real hook fires via a 1s one-shot timer

        assert calls, "memory_write tool-start-d must schedule _notify_memory_changed"


@pytest.mark.asyncio
async def test_non_memory_tool_event_does_not_schedule_a_refresh():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        calls = []
        app._notify_memory_changed = lambda: calls.append(True)

        raw = json.dumps({
            "ts": "2026-07-25T00:00:00Z", "flag": "tool-start-d",
            "payload": {"tool": "read_session", "tier": 0},
        })
        app._render_event(raw)
        await pilot.pause(1.2)

        assert not calls


# ── reward-flash-d ───────────────────────────────────────────────────────
# Kevin, 2026-07-26: "when the metrics go up add plus reward points beside
# the metric that increases. It can show for a few seconds and then go
# away. So we can see her getting rewarded for growth and for her working."

def _fake_health(**over):
    from sovereign_agent.stewardship.memory_garden import MemoryHealth
    base = dict(atoms_active=5, atoms_total=5, patterns_active=1,
                patterns_dormant=0, patterns_valuable=1, honor_notes=0,
                field_notes=0, provenance_entries=0, corrections=0,
                total_memories=10)
    base.update(over)
    return MemoryHealth(**base)


@pytest.mark.asyncio
async def test_first_survey_ever_establishes_baseline_without_a_flash(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.stewardship import memory_garden

    monkeypatch.setattr(memory_garden, "survey_memory", lambda d: _fake_health())

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        await pilot.pause(); await pilot.pause()
        assert app._memory_metric_flash == {}


@pytest.mark.asyncio
async def test_metric_increase_renders_a_plus_delta_badge(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.stewardship import memory_garden

    state = {"atoms": 5}
    monkeypatch.setattr(memory_garden, "survey_memory",
                        lambda d: _fake_health(atoms_active=state["atoms"],
                                               atoms_total=state["atoms"]))

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        await pilot.pause(); await pilot.pause()

        written = []
        orig_write = app._memory_log.write
        monkeypatch.setattr(app._memory_log, "write",
                            lambda s, *a, **k: (written.append(str(s)), orig_write(s, *a, **k))[-1])

        state["atoms"] = 8
        app._refresh_memory_pane()
        await pilot.pause(); await pilot.pause()

        atoms_lines = [l for l in written if "active: 8" in l]
        assert any("+3" in l for l in atoms_lines), atoms_lines
        assert app._memory_metric_flash["atoms_active"][0] == 3


@pytest.mark.asyncio
async def test_flash_badge_expires_after_its_window(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.stewardship import memory_garden
    import time

    state = {"atoms": 5}
    monkeypatch.setattr(memory_garden, "survey_memory",
                        lambda d: _fake_health(atoms_active=state["atoms"],
                                               atoms_total=state["atoms"]))

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        await pilot.pause(); await pilot.pause()

        state["atoms"] = 8
        app._refresh_memory_pane()
        await pilot.pause(); await pilot.pause()
        assert "atoms_active" in app._memory_metric_flash

        # simulate the flash window having elapsed
        app._memory_metric_flash["atoms_active"] = (3, time.time() - 999)

        written = []
        orig_write = app._memory_log.write
        monkeypatch.setattr(app._memory_log, "write",
                            lambda s, *a, **k: (written.append(str(s)), orig_write(s, *a, **k))[-1])
        app._refresh_memory_pane()
        await pilot.pause(); await pilot.pause()

        atoms_lines = [l for l in written if "active: 8" in l]
        assert atoms_lines and not any("+3" in l for l in atoms_lines)
