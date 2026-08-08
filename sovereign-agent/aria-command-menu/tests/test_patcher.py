"""Text-transform tests for aria-command-menu's patcher.py — proves the
app.py patch (8 anchored edits) applies cleanly against the CURRENT live
file, is idempotent, and the patched result compiles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher import MARK, MENU_BTN_MARK, patch_app, patch_menu_button_click  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PY = REPO_ROOT / "src" / "sovereign_agent" / "cockpit" / "app.py"


def test_patch_app_applies_and_is_idempotent():
    # `changed` is False if live src/ is already patched (this suite may run
    # again post-apply, e.g. via verify_module.sh) — either way `once` must
    # end up in the patched state, which is what the rest of this test checks.
    text = APP_PY.read_text(encoding="utf-8")
    once, _ = patch_app(text)
    assert MARK in once
    assert "CommandPaletteScreen" in once
    assert "action_command_palette" in once
    assert "palette-menu-btn" in once
    assert "_refresh_cockpit_strips" in once
    assert '"sov sentinels scan"' in once
    assert '"sov dream list"' in once
    assert '"sov requests list --all"' in once
    assert '"sentinels",\n' in once  # added to _KNOWN_SOV_SUBCOMMANDS
    assert MENU_BTN_MARK in once  # the "☰ commands" button click fix
    twice, changed_again = patch_app(once)
    assert not changed_again
    assert twice == once


def test_menu_button_click_fix_is_idempotent_and_present():
    """Regression test for a real bug Kevin found live: on_button_pressed
    only acted on CommandButton instances, so clicking the plain-Button
    "☰ commands" trigger did nothing (only Ctrl+M worked). Confirms the
    fix is present and re-applying it is a safe no-op."""
    text = APP_PY.read_text(encoding="utf-8")
    once, _ = patch_menu_button_click(text)
    assert MENU_BTN_MARK in once
    assert 'getattr(button, "id", None) == "palette-menu-btn"' in once
    twice, changed_again = patch_menu_button_click(once)
    assert not changed_again
    assert twice == once


def test_patched_app_compiles():
    import py_compile
    import tempfile

    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(patched)
        tmp_name = fh.name
    py_compile.compile(tmp_name, doraise=True)


def test_old_palette_rows_2_and_3_are_gone():
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    assert 'id="palette-row-2"' not in patched
    assert 'id="palette-row-3"' not in patched
    assert 'id="palette-row"' in patched  # the one remaining row


def test_all_palette_commands_and_reference_buttons_still_referenced():
    """Every command must still be reachable — just via CommandPaletteScreen
    instead of 3 permanent rows. This asserts app.py's own PALETTE_COMMANDS/
    REFERENCE_BUTTONS tuples are untouched by the patch (only the compose()
    rendering changed) — the command_palette_screen.py payload is what
    actually iterates them at popup-render time."""
    text = APP_PY.read_text(encoding="utf-8")
    patched, _ = patch_app(text)
    assert "PALETTE_COMMANDS: tuple[PaletteCommand, ...] = (" in patched
    assert "REFERENCE_BUTTONS: tuple[PaletteCommand, ...] = (" in patched
