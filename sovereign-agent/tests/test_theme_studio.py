"""Tests for theme-studio-d — the Theme Studio (browse/create/edit/remove)
and the creator's per-area color build. Pure logic + UI smoke + save
round-trip through the real user_themes layer.
"""
from __future__ import annotations

import pytest

from sovereign_agent.cockpit import user_themes as ut
from sovereign_agent.cockpit.theme_creator_screen import (
    COLOR_PALETTE,
    SLOTS,
    _options_for,
    theme_from_selections,
)
from sovereign_agent.cockpit.theme_studio_screen import cycle_index


# ── pure carousel ────────────────────────────────────────────────────────
def test_cycle_index_wraps_both_ways():
    assert cycle_index(0, 3, -1) == 2
    assert cycle_index(2, 3, 1) == 0
    assert cycle_index(1, 3, 1) == 2


def test_cycle_index_safe_on_empty():
    assert cycle_index(0, 0, 1) == 0
    assert cycle_index(5, 0, -1) == 0


# ── palette / build ──────────────────────────────────────────────────────
def test_palette_is_broad_and_covers_the_slots():
    assert len(COLOR_PALETTE) >= 30
    assert len(SLOTS) == 10  # every CockpitTheme color slot is editable


def test_options_include_the_current_value_even_if_off_palette():
    opts = _options_for("#123456")   # not in the palette
    values = [v for _, v in opts]
    assert "#123456" in values and values[0] == "#123456"


def test_theme_from_selections_builds_a_valid_theme():
    t = theme_from_selections("my-theme", "custom", True,
                              {s: "#22D3EE" for s, _ in SLOTS})
    assert ut.validate(t) == []
    assert t.name == "my-theme" and t.dark is True and t.primary == "#22D3EE"


def test_theme_defaults_fill_unset_slots():
    t = theme_from_selections("partial", "custom", True, {"primary": "#FB7185"})
    # unset slots fall back to the sensible dark default → still valid
    assert ut.validate(t) == []


# ── save round-trip (real user_themes layer, tmp dir) ───────────────────
def test_created_theme_saves_and_reloads(tmp_path):
    t = theme_from_selections("studio-made", "custom", True,
                              {s: "#A78BFA" for s, _ in SLOTS})
    ut.save(t, tmp_path)
    names = [x.name for x in ut.list_all(tmp_path)]
    assert "studio-made" in names
    loaded = ut.load("studio-made", tmp_path)
    assert loaded is not None and loaded.primary == "#A78BFA"


def test_soft_cap_is_high_and_never_refuses(tmp_path):
    # the cap is a warning threshold only — save must succeed regardless.
    assert ut.SOFT_CAP >= 500
    t = theme_from_selections("cap-test", "custom", True,
                              {s: "#4ADE80" for s, _ in SLOTS})
    ut.save(t, tmp_path)  # must not raise
    assert ut.load("cap-test", tmp_path) is not None


def test_delete_removes_a_custom_theme(tmp_path):
    t = theme_from_selections("to-remove", "custom", True,
                              {s: "#F97316" for s, _ in SLOTS})
    ut.save(t, tmp_path)
    assert ut.delete("to-remove", tmp_path) is True
    assert ut.load("to-remove", tmp_path) is None


# ── UI smoke ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_studio_opens_and_arrows_change_the_theme():
    from textual.widgets import Button

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        assert isinstance(app.screen, ThemeStudioScreen)
        before = app.theme
        await pilot.click(app.screen.query_one("#theme-next", Button))
        await pilot.pause()
        assert app.theme != before   # arrow applied a different preset live


@pytest.mark.asyncio
async def test_creator_opens_and_previews_live():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeCreatorScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_create()
        await pilot.pause()
        assert isinstance(app.screen, ThemeCreatorScreen)
        assert "__preview__" in app.available_themes   # live preview registered
