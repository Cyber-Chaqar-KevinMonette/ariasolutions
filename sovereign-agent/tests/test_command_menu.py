"""Behavior tests for aria-command-menu (Workstream M) — tests the REAL,
already-patched `sovereign_agent.cockpit.app` directly, no shadow copy, no
`sys.modules` manipulation.

This file originally used a shadow-copy-and-patch mechanism (needed only to
verify the patch function itself BEFORE the code was applied to live). Once
applied, that mechanism was unnecessary — and it turned out to be actively
harmful: the save/delete/restore `sys.modules` dance it used decoupled
shared module-level state across tests (confirmed while building
aria-security-strip-wire, a later patch to this same file, which hit the
exact same class of pollution bug already fixed once this session in
`test_locator_events_fix.py`). Root-cause fix: don't do it — test the real,
live module directly, exactly like `test_cockpit.py` does. The staged
`aria-command-menu/tests/test_command_menu.py` (never promoted) keeps the
shadow-copy mechanism, which is legitimate there for pre-apply verification.
"""
from __future__ import annotations

import pytest


def test_patched_cockpit_imports_cleanly():
    from sovereign_agent.cockpit.app import CommandPaletteScreen
    from sovereign_agent.cockpit import CockpitApp
    assert CockpitApp is not None
    assert CommandPaletteScreen is not None


@pytest.mark.asyncio
async def test_clicking_the_actual_trigger_button_opens_the_popup():
    """Regression test for a real bug Kevin found live: every other test in
    this file opened the popup via `app.action_command_palette()` directly,
    never by actually clicking the "☰ commands" button — so a bug where the
    button's own click handler did nothing (on_button_pressed only acted on
    CommandButton instances; the trigger is a plain Button) went undetected.
    This test clicks the real button, exactly as an operator would."""
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandPaletteScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        assert not isinstance(app.screen, CommandPaletteScreen)

        trigger = app.query_one("#palette-menu-btn", Button)
        await pilot.click(trigger)
        await pilot.pause()

        assert isinstance(app.screen, CommandPaletteScreen)

        # Clicking it again while already open must close it (toggle).
        # The trigger button lives on the base screen, not the popup, so
        # go through the binding to close — mirrors how an operator would
        # press Ctrl+M again or Esc.
        app.action_command_palette()
        await pilot.pause()
        assert app.screen is base_screen


@pytest.mark.asyncio
async def test_command_palette_popup_opens_lists_all_commands_and_closes():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import (
        PALETTE_COMMANDS,
        REFERENCE_BUTTONS,
        CommandButton,
        CommandPaletteScreen,
    )

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_command_palette()
        await pilot.pause()
        assert isinstance(app.screen, CommandPaletteScreen)

        buttons = app.screen.query(CommandButton)
        assert len(list(buttons)) == len(PALETTE_COMMANDS) + len(REFERENCE_BUTTONS)

        app.action_command_palette()  # toggle closed (same binding, screen already open)
        await pilot.pause()
        assert app.screen is base_screen


@pytest.mark.asyncio
async def test_clicking_a_command_pastes_and_closes_popup():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton
    from textual.widgets import Input

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        base_screen = app.screen
        app.action_command_palette()
        await pilot.pause()

        doctor_button = next(
            b for b in app.screen.query(CommandButton) if b.palette_cmd.key == "doctor"
        )
        await pilot.click(doctor_button)
        await pilot.pause()

        assert app.screen is base_screen  # popup auto-closed
        input_box = app.query_one("#input-box", Input)
        assert input_box.value == "sov doctor"


@pytest.mark.asyncio
async def test_new_missing_buttons_are_reachable_and_paste_correctly():
    """The 3 buttons found by the palette gap-audit (sentinels/dream/
    requests-all) must actually be clickable from the popup, same as any
    pre-existing command."""
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton, CommandPaletteScreen
    from textual.widgets import Input

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_command_palette()
        await pilot.pause()

        keys_to_commands = {
            "sentinels": "sov sentinels scan",
            "dream-list": "sov dream list",
            "requests-all": "sov requests list --all",
        }
        for key, expected_cmd in keys_to_commands.items():
            if not isinstance(app.screen, CommandPaletteScreen):
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


def test_sentinels_subcommand_now_recognized():
    from sovereign_agent.cockpit.app import normalize_sov_prefix

    result = normalize_sov_prefix("sov sentinels scan")
    assert result is not None
    assert result.kind == "execute"


@pytest.mark.asyncio
async def test_strips_render_without_throwing_on_empty_data():
    """The 3 new strips must never block cockpit boot even if their backing
    data is empty/absent — mirrors _refresh_inbox_pane's own discipline."""
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import Static

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        obs = app.query_one("#observability-strip", Static)
        sec = app.query_one("#security-strip", Static)
        emo = app.query_one("#emotions-strip", Static)
        # Rendered on mount via call_after_refresh — should be non-crashing
        # and non-empty (either real data or a graceful "(unavailable)" line).
        for strip in (obs, sec, emo):
            rendered = strip.render()
            assert rendered is not None


@pytest.mark.asyncio
async def test_sentinel_transitions_seeds_baseline_silently_on_first_call():
    """Regression test for a real flake this workstream's own build found:
    _check_sentinel_transitions used to compare the FIRST-ever read against
    an assumed 'ok' baseline it never actually observed, so any non-'ok'
    sentinel (normal on a fresh/empty data dir) fired a spurious 'regression'
    alert into chat on cockpit startup. The fix: seed silently on the first
    call — no alert — then alert normally on genuine later transitions."""
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.registry import gather_health

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        chat = app.query_one("#chat-log", RichLog)
        lines_before = len(chat.lines)

        # anti-lag-d: _check_sentinel_transitions no longer gathers health
        # itself (that redundant main-thread gather was the actual cause of
        # the periodic cockpit freeze) — it now takes the already-gathered
        # list as a parameter, exactly as _refresh_status_worker passes it
        # from _read_status's single, thread-offloaded gather.
        #
        # First call: must seed _prev_sentinel_states without writing any
        # "SENTINEL ALERT" line, even though a fresh tmp data dir will have
        # non-"ok" sentinels.
        statuses = gather_health(SETTINGS.paths.data_dir)
        app._check_sentinel_transitions(statuses)
        await pilot.pause()
        assert app._prev_sentinel_states  # baseline was seeded
        assert not any("SENTINEL ALERT" in str(line) for line in chat.lines[lines_before:])

        # A genuine transition (ok -> error) on a KNOWN sentinel must still
        # alert normally — the fix only skips the fabricated first-call case.
        app._prev_sentinel_states["some-sentinel"] = "ok"
        from sovereign_agent.stewardship.base import HealthStatus

        fake_statuses = [HealthStatus(sentinel_id="some-sentinel", level="error", summary="boom")]
        lines_before_2 = len(chat.lines)
        app._check_sentinel_transitions(fake_statuses)
        await pilot.pause()
        assert any("SENTINEL ALERT" in str(line) for line in chat.lines[lines_before_2:])


# ─── command-menu-glyph-fix-d (Kevin, 2026-07-21) ──────────────────────────
#
# "Here are some kind of cell width errors in the commands menu. It's
# bad." Screenshot showed literal garbled text like "🤖 bots"
# instead of a robot emoji, plus a visibly corrupted border. Root cause:
# REFERENCE_BUTTONS used JS/JSON-style UTF-16 SURROGATE-PAIR escapes
# ("🤖") for astral emoji -- invalid in a Python string literal
# (Python's \uXXXX is BMP-only; astral codepoints need \UXXXXXXXX), so
# Python held two unpaired surrogate code units that rendered as garbage
# -- AND the underlying emoji were Wide/emoji-risk regardless, exactly
# the class of bug glyphs.py's own doctrine describes ("any layout that
# counts characters... will be off-by-N"), explaining the corrupted
# border too.


def test_no_broken_surrogate_pair_escapes_in_reference_buttons():
    from sovereign_agent.cockpit.app import REFERENCE_BUTTONS

    for cmd in REFERENCE_BUTTONS:
        # A real (even if unpaired) surrogate code unit decodes to a
        # codepoint in this range -- catches the exact bug class, not
        # just today's three offenders.
        assert not any(0xD800 <= ord(ch) <= 0xDFFF for ch in cmd.label), (
            f"{cmd.label!r} contains a raw surrogate code unit"
        )


def test_reference_button_glyphs_are_all_actually_safe():
    from sovereign_agent import glyphs as _g
    from sovereign_agent.cockpit.app import REFERENCE_BUTTONS

    for cmd in REFERENCE_BUTTONS:
        icon = cmd.label.split(" ", 1)[0]
        if len(icon) != 1:
            continue  # plain-text label (e.g. "bots"), nothing to check
        assert _g.is_cataloged(icon) or not _g.audit_string(icon), (
            f"{cmd.label!r}'s icon {icon!r} is not a vetted-safe glyph"
        )
        assert not _g.is_emoji_risk(icon), (
            f"{cmd.label!r}'s icon {icon!r} is flagged emoji-risk"
        )


def test_model_menu_and_game_studio_are_reachable_from_the_commands_popup():
    """Kevin, 2026-07-21: "where is the configure models section?" --
    F8/`/model` existed but had no entry in the commands popup, the one
    place he was actually looking. Same gap existed for Game Studio
    (action="games" was already wired in the dispatch table but had no
    palette entry at all, unreachable from the popup)."""
    from sovereign_agent.cockpit.app import REFERENCE_BUTTONS

    actions = {cmd.action for cmd in REFERENCE_BUTTONS}
    assert "model_menu" in actions
    assert "games" in actions


@pytest.mark.asyncio
async def test_clicking_the_model_reference_button_opens_the_model_menu():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CommandButton, ModelMenuScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_command_palette()
        await pilot.pause()
        model_btn = next(
            b for b in app.screen.query(CommandButton)
            if b.palette_cmd.action == "model_menu"
        )
        # Dispatch the real Pressed message directly to CockpitApp's own
        # on_button_pressed (CommandPaletteScreen's handler only reacts
        # to its own exit button and lets a CommandButton press bubble
        # up to the app) rather than a pixel click -- this button sits
        # below the fold in the scrollable popup at the default test
        # terminal size, so a coordinate click is flaky; this still
        # exercises the actual handler.
        app.on_button_pressed(Button.Pressed(model_btn))
        await pilot.pause()
        assert isinstance(app.screen, ModelMenuScreen)
