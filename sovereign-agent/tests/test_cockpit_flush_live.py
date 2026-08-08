"""Behavior tests for aria-cockpit-flush, promoted to live tests/ — tests
the REAL, already-patched cockpit directly. Plain imports, no shadow copy,
no sys.modules manipulation.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_unmount_seals_buffered_chunk_turns():
    """The core guarantee: turns still buffered in the ChunkRecorder at
    shutdown are sealed by on_unmount, not silently lost."""
    from sovereign_agent.cockpit import CockpitApp

    sealed = []

    class _FakeRecorder:
        def seal_now(self, **kw):
            sealed.append(1)
            return None

    app = CockpitApp()
    async with app.run_test() as pilot:
        app._chunk_recorder = _FakeRecorder()
        await pilot.pause()
    # run_test's exit unmounts the app — the hook must have fired.
    assert sealed == [1]


@pytest.mark.asyncio
async def test_unmount_fsyncs_events(monkeypatch):
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent import events as events_module

    calls = []
    monkeypatch.setattr(events_module, "force_fsync", lambda: calls.append(1))

    app = CockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
    assert calls, "on_unmount did not call events.force_fsync()"


@pytest.mark.asyncio
async def test_unmount_survives_a_failing_recorder():
    """Best-effort discipline: a recorder that raises must not break
    shutdown (no exception escaping run_test's exit)."""
    from sovereign_agent.cockpit import CockpitApp

    class _ExplodingRecorder:
        def seal_now(self, **kw):
            raise RuntimeError("disk gone")

    app = CockpitApp()
    async with app.run_test() as pilot:
        app._chunk_recorder = _ExplodingRecorder()
        await pilot.pause()
    # Reaching here without an exception IS the assertion.


def test_error_handler_mentions_probe_in_source():
    """Cheap structural check on the live file: the mid-turn error handler
    consults probe_ollama for backend-shaped failures."""
    import inspect

    import sovereign_agent.cockpit.app as app_module

    src = inspect.getsource(app_module.CockpitApp._run_conversation_worker)
    assert "probe_ollama" in src
    assert "reason_phrase()" in src
