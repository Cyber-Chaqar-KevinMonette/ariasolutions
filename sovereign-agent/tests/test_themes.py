"""Tests for the curated theme spectrum.

The crash Kevin hit (CSS parse error when applying aria-cobalt, aria-crimson,
etc.) was caused by passing prose strings through Textual's `Theme.variables`
dict. The smoke test in the previous turn only verified import + construction,
which didn't catch it.

These tests actually MOUNT each theme in a headless Textual app and verify
that no stylesheet errors fire. This is the contract that locks the bug out.
"""
from __future__ import annotations

import pytest

from sovereign_agent.cockpit.themes import (
    CURATED_THEMES,
    CockpitTheme,
    themes_by_family,
    get_theme_by_name,
)


def test_full_spectrum_covered():
    """7 warm + 5 cool + 3 nature + 2 mono + 4 spectrum = 21."""
    assert len(CURATED_THEMES) == 21


def test_every_theme_has_unique_name():
    names = [t.name for t in CURATED_THEMES]
    assert len(names) == len(set(names))


def test_every_theme_name_starts_with_aria_prefix():
    """The prefix sorts our themes together in the picker, away from Textual built-ins."""
    for t in CURATED_THEMES:
        assert t.name.startswith("aria-"), f"theme {t.name} missing aria- prefix"


def test_get_theme_by_name_works():
    ember = get_theme_by_name("aria-ember")
    assert ember is not None
    assert ember.family == "warm"


def test_themes_by_family_groups_correctly():
    groups = themes_by_family()
    assert set(groups.keys()) == {"warm", "cool", "nature", "mono", "spectrum"}
    assert len(groups["warm"]) == 7
    assert len(groups["cool"]) == 5
    assert len(groups["nature"]) == 3
    assert len(groups["mono"]) == 2
    assert len(groups["spectrum"]) == 4  # aria-prism, aria-aurora, aria-nebula, aria-rainbow


def test_every_color_is_a_valid_hex():
    """Every color slot must be a valid #RRGGBB string (not a CSS variable
    or empty string), so Textual can parse it directly."""
    import re
    HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for t in CURATED_THEMES:
        for slot in ("background", "surface", "panel", "primary", "accent",
                     "secondary", "success", "warning", "error"):
            val = getattr(t, slot)
            assert val and HEX_RE.match(val), (
                f"theme {t.name} slot {slot} has invalid color: {val!r}"
            )
        # Optional slots: must be hex OR None
        for opt_slot in ("foreground", "boost"):
            val = getattr(t, opt_slot)
            if val is not None:
                assert HEX_RE.match(val), (
                    f"theme {t.name} slot {opt_slot} has invalid color: {val!r}"
                )


@pytest.mark.parametrize("theme_spec", CURATED_THEMES, ids=lambda t: t.name)
def test_theme_mounts_without_stylesheet_error(theme_spec: CockpitTheme):
    """The load-bearing test: each theme must mount in a real Textual app
    without raising a stylesheet error.

    This catches the class of bug that crashed aria-cobalt et al — anything
    in the theme that makes Textual's CSS parser unhappy at apply-time will
    fail this test, regardless of how the theme was constructed.
    """
    from textual.app import App

    class _Probe(App):
        def on_mount(self) -> None:
            # Register and apply the theme; exit before any UI renders.
            self.register_theme(theme_spec.to_textual_theme())
            self.theme = theme_spec.name
            self.exit()

    # run_test() drives the app headlessly. Any StylesheetError raised
    # during mount/apply propagates here.
    app = _Probe()
    import asyncio
    try:
        asyncio.run(_run_probe(app))
    except Exception as exc:
        pytest.fail(
            f"theme {theme_spec.name!r} failed to mount: "
            f"{type(exc).__name__}: {exc}"
        )


async def _run_probe(app):
    """Drive the probe app headlessly and surface any error."""
    async with app.run_test() as pilot:
        await pilot.pause()
