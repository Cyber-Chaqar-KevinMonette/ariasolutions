"""Cockpit integration tests for ⚡ the capability test menu.

Mirrors the house style in test_workflows_cockpit.py (Textual App.run_test +
Pilot). Real GPU/network calls are monkeypatched to cheap fakes throughout —
this file proves the UI WIRING (screen opens, buttons dispatch, live events
update reactive metrics, a finished run writes a report), not the real tools
themselves (those are covered directly in test_workflow_capability_tests.py).

`run_test(size=(120, 60))` is required (not the Textual default) — the modal
is tall enough that its footer buttons fall outside the default test-terminal
size, so `pilot.click()` silently misses them without an explicit larger size
(same precedent as tests/test_stripe_links_screen.py).
"""
from __future__ import annotations

import pytest

_SIZE = (120, 60)


def _fake_fns():
    from sovereign_agent.workflow import catalog as cat
    return {
        w.wid: (lambda ctx, _wid=w.wid: (f"fake pass for {_wid}", None))
        for w in cat.capability_testable_workflows()
    }


@pytest.mark.asyncio
async def test_slash_captest_pushes_capability_test_screen():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.capability_test_screen import CapabilityTestScreen
    from textual.widgets import Input
    app = CockpitApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        ib = app.query_one("#input-box")
        app.on_input_submitted(Input.Submitted(ib, "/captest", validation_result=None))
        await pilot.pause()
        assert isinstance(app.screen, CapabilityTestScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CapabilityTestScreen)


def test_captest_reference_button_wired_without_collision():
    """The ⚡ test button lives in REFERENCE_BUTTONS (an internal action, not
    a pasted command) with no key collision against the ⚙ menu or the
    palette — same invariant test_commands_popup_holds_everything_else_
    no_redundancy already checks for demo/workflows/etc."""
    from sovereign_agent.cockpit.app import PALETTE_COMMANDS, REFERENCE_BUTTONS
    entries = [c for c in REFERENCE_BUTTONS if c.action == "captest"]
    assert len(entries) == 1
    cmd = entries[0]
    assert cmd.command == "", "reference buttons carry an action, not a command"
    assert cmd.key not in {c.key for c in PALETTE_COMMANDS}


@pytest.mark.asyncio
async def test_captest_screen_renders_ready_and_gated_entries():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.capability_test_screen import (
        CapabilityTestScreen, _wid_to_id)
    from sovereign_agent.workflow import catalog as cat
    from textual.widgets import Button

    app = CockpitApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(CapabilityTestScreen())
        await pilot.pause()
        # every ready cap-testable workflow gets a real Test button
        for w in cat.capability_testable_workflows():
            btn = app.screen.query_one(f"#{_wid_to_id(w.wid)}", Button)
            assert btn is not None
        # a genuinely still-gated workflow is shown, but never gets a button
        # (create.video flipped to ready once LTX-Video was built and
        # confirmed live — voice.stt is still honestly gated)
        assert not app.screen.query(f"#{_wid_to_id('voice.stt')}")


@pytest.mark.asyncio
async def test_captest_run_all_button_updates_live_metrics_and_finishes(monkeypatch):
    from sovereign_agent.workflow import capability_tests as ct
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.capability_test_screen import CapabilityTestScreen
    from textual.widgets import Button

    app = CockpitApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(CapabilityTestScreen())
        await pilot.pause()
        run_all = app.screen.query_one("#captest-run-all", Button)
        await pilot.click(run_all)
        await pilot.pause()
        assert not app._captest_running, "capability test run never finished"
        screen = app.screen
        assert isinstance(screen, CapabilityTestScreen)
        assert screen.passed == len(ct.CAPABILITY_TEST_FNS)
        assert screen.failed == 0


@pytest.mark.asyncio
async def test_captest_single_test_button_runs_only_that_one(monkeypatch):
    from sovereign_agent.workflow import capability_tests as ct
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.capability_test_screen import (
        CapabilityTestScreen, _wid_to_id)
    from textual.widgets import Button

    app = CockpitApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(CapabilityTestScreen())
        await pilot.pause()
        wid = next(iter(ct.CAPABILITY_TEST_FNS))
        btn = app.screen.query_one(f"#{_wid_to_id(wid)}", Button)
        await pilot.click(btn)
        await pilot.pause()
        assert not app._captest_running
        screen = app.screen
        assert isinstance(screen, CapabilityTestScreen)
        assert screen.queued == 1
        assert screen.passed == 1


@pytest.mark.asyncio
async def test_captest_second_call_while_running_does_not_start_a_second_worker(monkeypatch):
    """The guard at the top of _captest_start must refuse a second call while
    one is already in progress -- tested against the guard's own logic
    (calling twice back-to-back with no await between, so a real background
    thread can't have finished in between either way) rather than racing a
    real thread's timing, which the test harness doesn't let us control."""
    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    calls = []
    monkeypatch.setattr(app, "_captest_worker", lambda selected_wids=None: calls.append(selected_wids))
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        app._captest_start(None)
        app._captest_start(None)   # immediately again -- no yield in between
        assert len(calls) == 1, "a second call while running must not start a second worker"


@pytest.mark.asyncio
async def test_captest_finished_writes_a_report_copy(monkeypatch, tmp_path):
    from sovereign_agent.workflow import capability_tests as ct
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())

    from sovereign_agent.cockpit import CockpitApp
    app = CockpitApp()
    monkeypatch.setattr(app, "_resolve_data_dir", lambda: tmp_path)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        app._captest_start(None)
        await pilot.pause()
        assert not app._captest_running
        reports = list((tmp_path / "reports").glob("capability-test-*.md"))
        assert reports, "expected a capability-test report written to data_dir/reports/"
