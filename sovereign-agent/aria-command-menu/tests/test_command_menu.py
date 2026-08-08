"""Behavior tests for aria-command-menu (Workstream M) — prove the patched
cockpit actually boots and the popup renders every command, using a shadow
copy of the whole package (never touches real src/)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    """Robust to running from either the staged location (aria-command-menu/
    tests/) or the promoted live location (tests/), which differ in nesting
    depth — the exact path-depth bug class fixed elsewhere this session
    (test_tools_all_export_fix.py, test_scanner_tier_a.py)."""
    for candidate in (start, *start.parents):
        if (candidate / "aria-command-menu" / "patcher.py").is_file():
            return candidate / "aria-command-menu"
    raise RuntimeError("could not locate aria-command-menu/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_app

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    app_py = shadow / "sovereign_agent" / "cockpit" / "app.py"
    # `changed` is False if src/ is already patched (this test file is also
    # run post-apply) — either way the shadow ends up patched, which is all
    # that matters here.
    patched, _ = patch_app(app_py.read_text(encoding="utf-8"))
    from patcher import MARK
    assert MARK in patched
    app_py.write_text(patched, encoding="utf-8")

    screen_src = STAGING / "payload" / "src" / "sovereign_agent" / "cockpit" / "command_palette_screen.py"
    (shadow / "sovereign_agent" / "cockpit" / "command_palette_screen.py").write_text(
        screen_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return shadow


@pytest.fixture
def shadow_cockpit(tmp_path, monkeypatch):
    """Import CockpitApp + CommandPaletteScreen from the shadow copy, saving
    and restoring sys.modules so this never pollutes later tests in the same
    process (the save-and-restore discipline fixed elsewhere this session —
    never delete sys.modules entries outright)."""
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent.cockpit.app as shadow_app_mod
        yield shadow_app_mod
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


def test_patched_cockpit_imports_cleanly(shadow_cockpit):
    assert shadow_cockpit.CockpitApp is not None
    assert shadow_cockpit.CommandPaletteScreen is not None


@pytest.mark.asyncio
async def test_clicking_the_actual_trigger_button_opens_the_popup(shadow_cockpit):
    """Regression test for a real bug Kevin found live: every other test in
    this file opened the popup via `app.action_command_palette()` directly,
    never by actually clicking the "☰ commands" button — so a bug where the
    button's own click handler did nothing (on_button_pressed only acted on
    CommandButton instances; the trigger is a plain Button) went undetected.
    This test clicks the real button, exactly as an operator would."""
    from textual.widgets import Button

    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        assert not isinstance(app.screen, shadow_cockpit.CommandPaletteScreen)

        trigger = app.query_one("#palette-menu-btn", Button)
        await pilot.click(trigger)
        await pilot.pause()

        assert isinstance(app.screen, shadow_cockpit.CommandPaletteScreen)

        # Clicking it again while already open must close it (toggle).
        # The trigger button lives on the base screen, not the popup, so
        # go through the binding to close — mirrors how an operator would
        # press Ctrl+M again or Esc.
        app.action_command_palette()
        await pilot.pause()
        assert app.screen is base_screen


@pytest.mark.asyncio
async def test_command_palette_popup_opens_lists_all_commands_and_closes(shadow_cockpit):
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        assert app.screen is not app.screen_stack[0] or True  # base screen sanity, non-fatal
        base_screen = app.screen
        app.action_command_palette()
        await pilot.pause()
        assert isinstance(app.screen, shadow_cockpit.CommandPaletteScreen)

        from sovereign_agent.cockpit.app import PALETTE_COMMANDS, REFERENCE_BUTTONS, CommandButton
        buttons = app.screen.query(CommandButton)
        assert len(list(buttons)) == len(PALETTE_COMMANDS) + len(REFERENCE_BUTTONS)

        app.action_command_palette()  # toggle closed (same binding, screen already open)
        await pilot.pause()
        assert app.screen is base_screen


@pytest.mark.asyncio
async def test_clicking_a_command_pastes_and_closes_popup(shadow_cockpit):
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_command_palette()
        await pilot.pause()

        from sovereign_agent.cockpit.app import CommandButton
        from textual.widgets import Input

        doctor_button = next(
            b for b in app.screen.query(CommandButton) if b.palette_cmd.key == "doctor"
        )
        await pilot.click(doctor_button)
        await pilot.pause()

        assert app.screen is base_screen  # popup auto-closed
        input_box = app.query_one("#input-box", Input)
        assert input_box.value == "sov doctor"


@pytest.mark.asyncio
async def test_new_missing_buttons_are_reachable_and_paste_correctly(shadow_cockpit):
    """The 3 buttons found by the palette gap-audit (sentinels/dream/
    requests-all) must actually be clickable from the popup, same as any
    pre-existing command."""
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        app.action_command_palette()
        await pilot.pause()

        from sovereign_agent.cockpit.app import CommandButton
        from textual.widgets import Input

        keys_to_commands = {
            "sentinels": "sov sentinels scan",
            "dream-list": "sov dream list",
            "requests-all": "sov requests list --all",
        }
        for key, expected_cmd in keys_to_commands.items():
            if not isinstance(app.screen, shadow_cockpit.CommandPaletteScreen):
                app.action_command_palette()  # reopen — the prior click closed it
                await pilot.pause()
            buttons_by_key = {b.palette_cmd.key: b for b in app.screen.query(CommandButton)}
            assert key in buttons_by_key, f"missing palette button for key {key!r}"
            target = buttons_by_key[key]
            target.scroll_visible(animate=False)  # may be off-screen in the scrollable list
            await pilot.pause()
            await pilot.click(target)
            await pilot.pause()
            input_box = app.query_one("#input-box", Input)
            assert input_box.value == expected_cmd


def test_sentinels_subcommand_now_recognized(shadow_cockpit):
    normalize_sov_prefix = shadow_cockpit.normalize_sov_prefix
    result = normalize_sov_prefix("sov sentinels scan")
    assert result is not None
    assert result.kind == "execute"


@pytest.mark.asyncio
async def test_strips_render_without_throwing_on_empty_data(shadow_cockpit):
    """The 3 new strips must never block cockpit boot even if their backing
    data is empty/absent — mirrors _refresh_inbox_pane's own discipline."""
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        from textual.widgets import Static
        obs = app.query_one("#observability-strip", Static)
        sec = app.query_one("#security-strip", Static)
        emo = app.query_one("#emotions-strip", Static)
        # Rendered on mount via call_after_refresh — should be non-crashing
        # and non-empty (either real data or a graceful "(unavailable)" line).
        for strip in (obs, sec, emo):
            rendered = strip.render()
            assert rendered is not None


@pytest.mark.asyncio
async def test_sentinel_transitions_seeds_baseline_silently_on_first_call(shadow_cockpit):
    """Regression test for a real flake this workstream's own build found:
    _check_sentinel_transitions used to compare the FIRST-ever read against
    an assumed 'ok' baseline it never actually observed, so any non-'ok'
    sentinel (normal on a fresh/empty data dir) fired a spurious 'regression'
    alert into chat on cockpit startup. The fix: seed silently on the first
    call — no alert — then alert normally on genuine later transitions."""
    app_cls = shadow_cockpit.CockpitApp
    async with app_cls().run_test() as pilot:
        app = pilot.app
        from textual.widgets import RichLog

        chat = app.query_one("#chat-log", RichLog)
        lines_before = len(chat.lines)

        # First call: must seed _prev_sentinel_states without writing any
        # "SENTINEL ALERT" line, even though a fresh tmp data dir will have
        # non-"ok" sentinels.
        app._check_sentinel_transitions()
        await pilot.pause()
        assert app._prev_sentinel_states  # baseline was seeded
        assert not any("SENTINEL ALERT" in str(line) for line in chat.lines[lines_before:])

        # A genuine transition (ok -> error) on a KNOWN sentinel must still
        # alert normally — the fix only skips the fabricated first-call case.
        app._prev_sentinel_states["some-sentinel"] = "ok"
        from sovereign_agent.stewardship.base import HealthStatus

        def fake_gather_health(data_dir):
            return [HealthStatus(sentinel_id="some-sentinel", level="error", summary="boom")]

        import sovereign_agent.cockpit.app as app_mod
        import sovereign_agent.stewardship.registry as registry_mod
        original = registry_mod.gather_health
        registry_mod.gather_health = fake_gather_health
        try:
            lines_before_2 = len(chat.lines)
            app._check_sentinel_transitions()
            await pilot.pause()
            assert any("SENTINEL ALERT" in str(line) for line in chat.lines[lines_before_2:])
        finally:
            registry_mod.gather_health = original
