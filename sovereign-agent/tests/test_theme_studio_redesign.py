"""Tests for theme-studio-redesign-d — the Theme Studio redesign (Kevin,
2026-07-20): list is the primary way to browse/preview themes, arrows are
an optional secondary way to step the SAME list, plus the ARROW_RIGHT_HEAVY
glyph-safety correction found while fixing the "4 unsafe glyphs" report."""
from __future__ import annotations

import pytest


# ── glyphs.py — ARROW_RIGHT_HEAVY was mislabeled safe, genuinely isn't ────

def test_arrow_right_heavy_is_east_asian_width_ambiguous():
    """The actual, measured Unicode property -- confirms this was never
    safe, not a false alarm."""
    import unicodedata
    from sovereign_agent.glyphs import ARROW_RIGHT_HEAVY
    assert unicodedata.east_asian_width(ARROW_RIGHT_HEAVY) == "A"


def test_arrow_right_heavy_is_no_longer_in_established_safe():
    from sovereign_agent.glyphs import ARROW_RIGHT_HEAVY, _ESTABLISHED_SAFE
    assert ARROW_RIGHT_HEAVY not in _ESTABLISHED_SAFE


def test_arrow_right_heavy_is_flagged_unsafe_by_audit_string():
    from sovereign_agent.glyphs import ARROW_RIGHT_HEAVY, audit_string
    assert audit_string(ARROW_RIGHT_HEAVY) != []


def test_arrow_right_and_arrow_left_remain_genuinely_safe():
    """The replacements used throughout this fix are the real safe pair."""
    from sovereign_agent.glyphs import ARROW_LEFT, ARROW_RIGHT, audit_string
    assert audit_string(ARROW_RIGHT) == []
    assert audit_string(ARROW_LEFT) == []


def test_tier_screen_no_longer_uses_the_unsafe_arrow():
    import inspect

    import sovereign_agent.cockpit.tier_screen as m
    src = inspect.getsource(m)
    assert "▶" not in src


def test_game_studio_screen_no_longer_imports_arrow_right_heavy():
    import inspect

    import sovereign_agent.cockpit.game_studio_screen as m
    src = inspect.getsource(m)
    assert "ARROW_RIGHT_HEAVY" not in src
    assert "▶" not in src


# ── ThemeStudioScreen — the redesigned list-primary picker ──────────────

@pytest.mark.asyncio
async def test_no_unsafe_glyphs_in_the_actual_code():
    """The module docstring legitimately DISCUSSES the fixed glyphs (that's
    documentation, same as glyphs.py itself documents unsafe glyphs on
    purpose) -- what must never contain them is the actual code below it."""
    import inspect

    import sovereign_agent.cockpit.theme_studio_screen as m
    src = inspect.getsource(m)
    code_only = src.split('"""', 2)[-1]  # drop the module's own top docstring
    for bad in ("◀", "▶", "✎", "\U0001f5d1", "＋", "●"):
        assert bad not in code_only, f"unsafe glyph {bad!r} still present in actual code"


def test_black_circle_marker_is_ambiguous_width_confirms_the_extra_fix():
    """● (U+25CF), copied from theme_picker_screen.py's own marker
    convention, was caught by this same redesign's own glyph audit --
    not part of Kevin's original 4/5, found while building this."""
    import unicodedata
    from sovereign_agent.glyphs import audit_string
    assert unicodedata.east_asian_width("●") == "A"
    assert audit_string("●") != []  # genuinely unsafe, not de-facto-narrow


@pytest.mark.asyncio
async def test_current_theme_marker_uses_the_safe_bullet():
    from textual.widgets import OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen
    from sovereign_agent.glyphs import BULLET

    from sovereign_agent.cockpit.themes import CURATED_THEMES

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        active = CURATED_THEMES[0].name  # a known preset, regardless of the test env's default
        app.theme = active
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        option_list = screen.query_one("#theme-list", OptionList)
        found_marker = False
        for i in range(option_list.option_count):
            opt = option_list.get_option_at_index(i)
            if opt.id == f"theme-preset::{active}":
                assert BULLET in str(opt.prompt)
                assert "●" not in str(opt.prompt)
                found_marker = True
        assert found_marker


@pytest.mark.asyncio
async def test_list_shows_presets_and_customs_with_headers():
    from textual.widgets import OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        assert isinstance(app.screen, ThemeStudioScreen)
        option_list = app.screen.query_one("#theme-list", OptionList)
        assert option_list.option_count > 0
        ids = [option_list.get_option_at_index(i).id for i in range(option_list.option_count)]
        assert "header-presets" in ids
        assert "header-custom" in ids


@pytest.mark.asyncio
async def test_highlighting_an_option_previews_live():
    from textual.widgets import OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        option_list = screen.query_one("#theme-list", OptionList)

        preset_index = None
        for i in range(option_list.option_count):
            opt = option_list.get_option_at_index(i)
            if opt.id and opt.id.startswith("theme-preset::"):
                preset_index = i
                break
        assert preset_index is not None
        target_name = option_list.get_option_at_index(preset_index).id.split("::", 1)[1]

        option_list.highlighted = preset_index
        await pilot.pause()
        assert app.theme == target_name


@pytest.mark.asyncio
async def test_escape_without_choosing_reverts_to_original_theme():
    from textual.widgets import OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        original = app.theme
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        option_list = screen.query_one("#theme-list", OptionList)

        for i in range(option_list.option_count):
            opt = option_list.get_option_at_index(i)
            if opt.id and opt.id.startswith("theme-preset::") and not opt.id.endswith(f"::{original}"):
                option_list.highlighted = i
                break
        await pilot.pause()
        assert app.theme != original  # confirms the preview actually changed it

        await pilot.press("escape")
        await pilot.pause()
        assert app.theme == original  # reverted


@pytest.mark.asyncio
async def test_selecting_an_option_commits_and_persists():
    from textual.widgets import OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen
    from sovereign_agent.cockpit import user_themes as ut
    from sovereign_agent.config import SETTINGS

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        option_list = screen.query_one("#theme-list", OptionList)

        preset_index = None
        for i in range(option_list.option_count):
            opt = option_list.get_option_at_index(i)
            if opt.id and opt.id.startswith("theme-preset::"):
                preset_index = i
                break
        target_name = option_list.get_option_at_index(preset_index).id.split("::", 1)[1]
        option_list.highlighted = preset_index

        option_list.action_select()
        await pilot.pause()

        assert ut.get_active_theme_name(SETTINGS.paths.data_dir) == target_name


@pytest.mark.asyncio
async def test_prev_next_buttons_move_the_same_cursor():
    from textual.widgets import Button, OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        option_list = screen.query_one("#theme-list", OptionList)
        start = option_list.highlighted

        next_btn = screen.query_one("#theme-next", Button)
        next_btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(next_btn)
        await pilot.pause()
        assert option_list.highlighted != start  # the button moved the SAME list cursor


@pytest.mark.asyncio
async def test_edit_targets_the_highlighted_custom_theme():
    from textual.widgets import OptionList

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen
    from sovereign_agent.cockpit import user_themes as ut
    from sovereign_agent.cockpit.user_themes import UserTheme
    from sovereign_agent.config import SETTINGS

    ut.save(UserTheme(
        name="my-custom-test-theme", family="custom", mood="test", dark=True,
        background="#000000", surface="#111111", panel="#222222",
        primary="#123456", accent="#234567", secondary="#345678",
        success="#00ff00", warning="#ffff00", error="#ff0000",
    ), SETTINGS.paths.data_dir)

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        option_list = screen.query_one("#theme-list", OptionList)

        custom_index = None
        for i in range(option_list.option_count):
            opt = option_list.get_option_at_index(i)
            if opt.id == "theme-custom::my-custom-test-theme":
                custom_index = i
                break
        assert custom_index is not None
        option_list.highlighted = custom_index

        assert screen._highlighted_custom_name() == "my-custom-test-theme"


@pytest.mark.asyncio
async def test_edit_without_a_custom_selected_toasts_instead_of_crashing():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import ThemeStudioScreen

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        app.action_theme_studio()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemeStudioScreen)
        screen._edit_current_custom()  # no custom theme highlighted -> must not raise
