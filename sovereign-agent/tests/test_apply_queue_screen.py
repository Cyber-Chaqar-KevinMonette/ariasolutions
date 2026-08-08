"""Tests for cockpit/apply_queue_screen.py — the "Queue & Quit" one-button
same-terminal apply handoff, and cockpit/app.py's run() exec-handoff mechanism."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── ApplyQueueScreen._queue_selected() return value ─────────────────────────


def test_pending_modules_uses_shared_staged_status(tmp_path):
    from sovereign_agent.cockpit.apply_queue_screen import _pending_modules
    from sovereign_agent import staged_status

    assert _pending_modules is staged_status.pending_modules


# ── the "Queue & Quit" button: enqueue then exit, in that order ────────────


async def test_queue_and_quit_button_enqueues_then_sets_exit_flag(tmp_path, monkeypatch):
    from sovereign_agent.cockpit.app import CockpitApp, ApplyQueueScreen
    from sovereign_agent.apply_queue.store import ApplyQueueStore

    mod_dir = tmp_path / "aria-fake-module"
    (mod_dir).mkdir()
    (mod_dir / "apply_fake_module.sh").write_text("#!/bin/bash\necho hi\n")

    store = ApplyQueueStore(root=tmp_path / "queue_root")
    app = CockpitApp()
    async with app.run_test() as pilot:
        screen = ApplyQueueScreen(tmp_path)
        with patch.object(ApplyQueueScreen, "_store", return_value=store):
            await app.push_screen(screen)
            await pilot.pause()

            sel_list = screen.query_one("#aq-list")
            sel_list.select("aria-fake-module")
            await pilot.pause()

            assert not getattr(app, "_run_queue_on_exit", False)
            await pilot.click("#aq-queue-quit")
            await pilot.pause()

    assert getattr(app, "_run_queue_on_exit", False) is True
    active = store.active()
    assert any(it.slug == "aria-fake-module" for it in active)


async def test_queue_and_quit_does_not_exit_when_nothing_selected(tmp_path):
    from sovereign_agent.cockpit.app import CockpitApp, ApplyQueueScreen
    from sovereign_agent.apply_queue.store import ApplyQueueStore

    store = ApplyQueueStore(root=tmp_path / "queue_root")
    app = CockpitApp()
    async with app.run_test() as pilot:
        screen = ApplyQueueScreen(tmp_path)
        with patch.object(ApplyQueueScreen, "_store", return_value=store):
            await app.push_screen(screen)
            await pilot.pause()
            # nothing selected — clicking Queue & Quit must not set the exit flag
            await pilot.click("#aq-queue-quit")
            await pilot.pause()

    assert not getattr(app, "_run_queue_on_exit", False)
    assert store.active() == []


# ── run()'s exec-handoff: replaces the process, doesn't spawn a child ──────


def test_run_execs_apply_queue_run_when_flag_set(tmp_path, monkeypatch):
    from sovereign_agent.cockpit import app as app_module

    script = tmp_path / "scripts" / "apply_queue_run.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n")

    fake_app = type("FakeApp", (), {})()
    fake_app._run_queue_on_exit = True
    fake_app.run = lambda: None

    with patch.object(app_module, "CockpitApp", return_value=fake_app), \
         patch("sovereign_agent.__file__", str(tmp_path / "src" / "sovereign_agent" / "__init__.py")), \
         patch("os.execvp") as mock_exec:
        app_module.run()

    mock_exec.assert_called_once_with("bash", ["bash", str(script)])


def test_run_does_not_exec_when_flag_unset():
    from sovereign_agent.cockpit import app as app_module

    fake_app = type("FakeApp", (), {})()
    fake_app.run = lambda: None
    # deliberately no _run_queue_on_exit attribute at all

    with patch.object(app_module, "CockpitApp", return_value=fake_app), \
         patch("os.execvp") as mock_exec:
        app_module.run()

    mock_exec.assert_not_called()
