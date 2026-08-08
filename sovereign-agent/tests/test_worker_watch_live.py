"""Behavior tests for aria-worker-watch, promoted to live tests/."""
from __future__ import annotations

import pytest


class _FakeWorker:
    def __init__(self, group):
        self.group = group


class _FakeEvent:
    def __init__(self, group, state):
        self.worker = _FakeWorker(group)
        self.state = state


@pytest.mark.asyncio
async def test_dead_persistent_worker_respawns_bounded_then_latches():
    from textual.worker import WorkerState

    import sovereign_agent.cockpit.app as app_module
    from sovereign_agent.cockpit import CockpitApp

    app_module._WORKER_RESPAWNS.clear()
    app_module._DEAD_WORKERS.clear()
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        respawned = []
        app._tail_events_worker = lambda: respawned.append("events")
        for _ in range(app_module._MAX_WORKER_RESPAWNS):
            app.on_worker_state_changed(_FakeEvent("events", WorkerState.ERROR))
        assert respawned == ["events"] * app_module._MAX_WORKER_RESPAWNS
        assert "events" not in app_module._DEAD_WORKERS
        # one more death → latch, no further respawn
        app.on_worker_state_changed(_FakeEvent("events", WorkerState.ERROR))
        assert len(respawned) == app_module._MAX_WORKER_RESPAWNS
        assert "events" in app_module._DEAD_WORKERS
        await pilot.pause()
        text = "\n".join(getattr(l, "text", str(l)) for l in app._chat_log.lines)
        assert "latched dead" in text
    app_module._WORKER_RESPAWNS.clear()
    app_module._DEAD_WORKERS.clear()


@pytest.mark.asyncio
async def test_success_of_a_while_true_loop_counts_as_death():
    """These loops never return normally — SUCCESS is a death too."""
    from textual.worker import WorkerState

    import sovereign_agent.cockpit.app as app_module
    from sovereign_agent.cockpit import CockpitApp

    app_module._WORKER_RESPAWNS.clear()
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        respawned = []
        app._heartbeat_worker = lambda: respawned.append("heart")
        app.on_worker_state_changed(_FakeEvent("heart", WorkerState.SUCCESS))
        assert respawned == ["heart"]
    app_module._WORKER_RESPAWNS.clear()


@pytest.mark.asyncio
async def test_unwatched_groups_and_running_states_ignored():
    from textual.worker import WorkerState

    import sovereign_agent.cockpit.app as app_module
    from sovereign_agent.cockpit import CockpitApp

    app_module._WORKER_RESPAWNS.clear()
    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.on_worker_state_changed(_FakeEvent("work-session", WorkerState.ERROR))
        app.on_worker_state_changed(_FakeEvent("events", WorkerState.RUNNING))
        assert app_module._WORKER_RESPAWNS == {}
