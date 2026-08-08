"""Tests for the hue cycling engine.

Locks in:
  - color math: hex → HLS → hex round-trips, hue rotation preserves S/L
  - config parsing: clamps speeds to sane bounds, filters never-rotate slots
  - aria-prism mounts cleanly with cycling configured
  - the engine respects the kill switch env var
  - the engine never crashes the host app on tick errors
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from sovereign_agent.cockpit.themes import get_theme_by_name
from sovereign_agent.cockpit.hue_cycle import (
    DEFAULT_ROTATABLE_SLOTS,
    HueCycleConfig,
    HueCycleEngine,
    KILL_SWITCH_ENV,
    NEVER_ROTATE_SLOTS,
    _hex_to_hls,
    _hls_to_hex,
    build_phase_theme,
    rotated_color,
)


# ─── color math ──────────────────────────────────────────────────────────


def test_hex_hls_roundtrip_is_stable():
    """Round-tripping a hex color through HLS and back must be identity
    (within ±1 RGB step for floating-point rounding)."""
    for hex_in in ["#FF6B9D", "#3D7EFF", "#10B981", "#000000", "#FFFFFF", "#7C7DFF"]:
        h, l, s = _hex_to_hls(hex_in)
        hex_out = _hls_to_hex(h, l, s)
        # Allow ±1 per channel for floating-point rounding
        r_in = int(hex_in[1:3], 16); r_out = int(hex_out[1:3], 16)
        g_in = int(hex_in[3:5], 16); g_out = int(hex_out[3:5], 16)
        b_in = int(hex_in[5:7], 16); b_out = int(hex_out[5:7], 16)
        assert abs(r_in - r_out) <= 1, f"R drift {hex_in} → {hex_out}"
        assert abs(g_in - g_out) <= 1, f"G drift {hex_in} → {hex_out}"
        assert abs(b_in - b_out) <= 1, f"B drift {hex_in} → {hex_out}"


def test_rotated_color_zero_offset_is_identity():
    """A hue offset of 0 should leave the color unchanged."""
    for hex_in in ["#FF6B9D", "#3D7EFF", "#10B981"]:
        out = rotated_color(hex_in, 0.0)
        # Allow ±1 per channel for fp rounding
        for i in (1, 3, 5):
            assert abs(int(hex_in[i:i+2], 16) - int(out[i:i+2], 16)) <= 1


def test_rotated_color_full_turn_returns_to_original():
    """A hue offset of 1.0 (full turn) is identity (modulo fp drift)."""
    hex_in = "#FF6B9D"
    out = rotated_color(hex_in, 1.0)
    for i in (1, 3, 5):
        assert abs(int(hex_in[i:i+2], 16) - int(out[i:i+2], 16)) <= 2


def test_rotated_color_changes_hue_at_half_turn():
    """A hue offset of 0.5 must produce a visibly different color."""
    hex_in = "#FF6B9D"  # rose-pink
    out = rotated_color(hex_in, 0.5)
    assert out != hex_in
    # Each channel should differ by more than the ±1 fp tolerance
    for i in (1, 3, 5):
        if abs(int(hex_in[i:i+2], 16) - int(out[i:i+2], 16)) > 5:
            return  # at least one channel changed substantially → pass
    pytest.fail(f"half-turn rotation didn't change color enough: {hex_in} → {out}")


# ─── config parsing ──────────────────────────────────────────────────────


def test_config_clamps_short_periods():
    """Periods < 10s would be a strobe hazard. Engine must clamp."""
    cfg = HueCycleConfig.from_dict({"period_seconds": 0.5, "tick_seconds": 0.01})
    assert cfg.period_seconds >= 10.0
    assert cfg.tick_seconds >= 0.5


def test_config_filters_never_rotate_slots():
    """Even if someone tries to rotate the background, defense in depth refuses."""
    cfg = HueCycleConfig.from_dict({
        "rotate_slots": ["primary", "background", "success", "accent"],
    })
    assert "background" not in cfg.rotate_slots
    assert "success" not in cfg.rotate_slots
    assert "primary" in cfg.rotate_slots
    assert "accent" in cfg.rotate_slots


def test_config_clamps_amplitude_to_unit_interval():
    cfg = HueCycleConfig.from_dict({"amplitude": 2.0})
    assert cfg.amplitude == 1.0
    cfg2 = HueCycleConfig.from_dict({"amplitude": -0.5})
    assert cfg2.amplitude == 0.0


def test_allow_background_opt_in_unlocks_structural_slots_only():
    """With allow_background, structural slots become rotatable — but the hard
    set (foreground + semantic colours) stays locked no matter what."""
    cfg = HueCycleConfig.from_dict({
        "allow_background": True,
        "rotate_slots": ["primary", "background", "surface", "panel",
                         "foreground", "success", "error"],
    })
    assert cfg.allow_background is True
    # structural slots now allowed
    assert "background" in cfg.rotate_slots
    assert "surface" in cfg.rotate_slots
    assert "panel" in cfg.rotate_slots
    # hard-locked slots never rotate, even when explicitly requested
    assert "foreground" not in cfg.rotate_slots
    assert "success" not in cfg.rotate_slots
    assert "error" not in cfg.rotate_slots


def test_rainbow_theme_background_rotates_but_stays_dark():
    """aria-rainbow opts into background rotation; the rotated background must
    differ from the base yet remain dark (lightness capped)."""
    import colorsys

    rainbow = get_theme_by_name("aria-rainbow")
    assert rainbow is not None
    config = HueCycleConfig.from_dict(rainbow.effects["hue_cycle"])
    phased = build_phase_theme(rainbow, config, phase=0.5)
    # background changed (it rotates)…
    assert phased.background != rainbow.background
    # …but stays dark: lightness under the cap (+ small fp tolerance)
    h = phased.background.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    _, light, _ = colorsys.rgb_to_hls(r, g, b)
    assert light <= config.dark_cap + 0.02
    # semantic + text stay fixed
    assert phased.error == rainbow.error
    assert phased.foreground == rainbow.foreground


# ─── theme rotation ──────────────────────────────────────────────────────


def test_build_phase_theme_rotates_only_configured_slots():
    """Background/surface/success must be untouched. Primary/accent move."""
    prism = get_theme_by_name("aria-prism")
    assert prism is not None
    config = HueCycleConfig.from_dict(prism.effects["hue_cycle"])

    phased = build_phase_theme(prism, config, phase=0.5)

    # Never-rotate slots are unchanged
    assert phased.background == prism.background
    assert phased.surface == prism.surface
    assert phased.success == prism.success
    assert phased.warning == prism.warning
    assert phased.error == prism.error
    # Rotated slots ARE changed (by half-turn)
    assert phased.primary != prism.primary
    assert phased.accent != prism.accent


def test_build_phase_theme_at_phase_zero_is_identity():
    """At phase=0, the rotated theme equals the base theme."""
    prism = get_theme_by_name("aria-prism")
    config = HueCycleConfig.from_dict(prism.effects["hue_cycle"])
    phased = build_phase_theme(prism, config, phase=0.0)
    for slot in ("primary", "accent", "secondary", "background", "surface"):
        # Allow ±1 RGB drift from fp roundtripping
        v_in = getattr(prism, slot); v_out = getattr(phased, slot)
        for i in (1, 3, 5):
            assert abs(int(v_in[i:i+2], 16) - int(v_out[i:i+2], 16)) <= 1


# ─── aria-prism end-to-end ───────────────────────────────────────────────


def test_aria_prism_is_in_curated_themes():
    """The spectrum theme must be discoverable by name."""
    prism = get_theme_by_name("aria-prism")
    assert prism is not None
    assert prism.family == "spectrum"
    assert "hue_cycle" in prism.effects


def test_aria_prism_mounts_cleanly_with_cycling():
    """The real load-bearing test: aria-prism mounts in a Textual app AND
    the cycling engine starts without error.

    This catches both classes of bug at once — the original variables-as-CSS
    crash AND any timer/registration issue with cycling.
    """
    from textual.app import App
    import asyncio

    class _Probe(App):
        def on_mount(self) -> None:
            from sovereign_agent.cockpit.themes import register_curated_themes
            from sovereign_agent.cockpit.hue_cycle import maybe_start_for_active_theme
            register_curated_themes(self)
            self.theme = "aria-prism"
            engine = maybe_start_for_active_theme(self, "aria-prism")
            # Engine should have started (unless kill switch is on, which it
            # shouldn't be in test environment)
            if not os.environ.get(KILL_SWITCH_ENV):
                assert engine is not None
                engine.stop()  # stop cleanly before exiting
            self.exit()

    async def _run():
        app = _Probe()
        async with app.run_test() as pilot:
            await pilot.pause()

    asyncio.run(_run())


# ─── kill switch ─────────────────────────────────────────────────────────


def test_kill_switch_disables_engine():
    """SOV_NO_HUE_CYCLE=1 must prevent the engine from starting."""
    from textual.app import App
    import asyncio

    class _Probe(App):
        def on_mount(self) -> None:
            from sovereign_agent.cockpit.themes import register_curated_themes
            from sovereign_agent.cockpit.hue_cycle import maybe_start_for_active_theme
            register_curated_themes(self)
            self.theme = "aria-prism"
            engine = maybe_start_for_active_theme(self, "aria-prism")
            # With kill switch on, engine.start() returned False → None
            assert engine is None, "kill switch should have prevented engine start"
            self.exit()

    async def _run():
        app = _Probe()
        async with app.run_test() as pilot:
            await pilot.pause()

    with patch.dict(os.environ, {KILL_SWITCH_ENV: "1"}):
        asyncio.run(_run())


def test_engine_fail_safe_on_tick_error():
    """If a tick raises, the engine must stop cleanly, not propagate."""
    from sovereign_agent.cockpit.hue_cycle import HueCycleEngine

    class _FakeApp:
        theme = "aria-prism"
        def register_theme(self, t): raise RuntimeError("simulated CSS failure")
        def set_interval(self, *a, **kw):
            class _Timer:
                def stop(self): pass
            return _Timer()

    cfg = HueCycleConfig.from_dict({"period_seconds": 60, "tick_seconds": 1})
    engine = HueCycleEngine(_FakeApp(), "aria-prism", cfg)
    engine._base = get_theme_by_name("aria-prism")
    engine._running = True
    # Calling _tick directly should NOT raise
    engine._tick()
    # Engine should have stopped itself
    assert engine._running is False


def test_engine_tick_actually_triggers_css_refresh():
    """REGRESSION TEST for the "colors aren't moving" bug.

    The original implementation set `self.app.theme = self.theme_name`
    after re-registering, but Textual's reactive system saw the string
    was unchanged and skipped the watcher entirely. No refresh fired.

    A working engine MUST invoke _invalidate_css() and refresh_css() to
    force Textual to re-apply the freshly-registered (different-colored)
    theme.
    """
    from sovereign_agent.cockpit.hue_cycle import HueCycleEngine

    invalidate_calls = []
    refresh_calls = []
    register_calls = []

    class _FakeApp:
        theme = "aria-prism"
        def register_theme(self, t):
            register_calls.append(t)
        def _invalidate_css(self):
            invalidate_calls.append(True)
        def refresh_css(self, animate=False):
            refresh_calls.append({"animate": animate})

    cfg = HueCycleConfig.from_dict({"period_seconds": 60, "tick_seconds": 1})
    engine = HueCycleEngine(_FakeApp(), "aria-prism", cfg)
    engine._base = get_theme_by_name("aria-prism")
    engine._running = True

    # Drive 3 ticks
    engine._tick()
    engine._tick()
    engine._tick()

    # Each tick must: (a) re-register the theme, (b) invalidate CSS,
    # (c) call refresh_css with animate=False
    assert len(register_calls) == 3, f"expected 3 re-registers, got {len(register_calls)}"
    assert len(invalidate_calls) == 3, f"expected 3 invalidates, got {len(invalidate_calls)}"
    assert len(refresh_calls) == 3, f"expected 3 refreshes, got {len(refresh_calls)}"
    assert all(r["animate"] is False for r in refresh_calls), "refresh must be non-animated"


def test_differential_rotation_makes_slots_move_independently():
    """The prism magic: each slot rotates at its own speed.

    At any phase > 0, primary, accent, and secondary should have shifted
    by DIFFERENT amounts — that's what gives the cockpit its prismatic
    feel rather than a uniform color wheel rotation.
    """
    prism = get_theme_by_name("aria-prism")
    config = HueCycleConfig.from_dict(prism.effects["hue_cycle"])

    # The config must declare differential speeds
    assert config.speed_for("primary") != config.speed_for("accent"), \
        "primary and accent must rotate at different rates"
    assert config.speed_for("secondary") < 0, \
        "secondary must rotate in the opposite direction for prismatic effect"


def test_aurora_theme_exists_with_smaller_amplitude():
    """The second spectrum theme: gentler, stays in cool hues."""
    aurora = get_theme_by_name("aria-aurora")
    assert aurora is not None
    assert aurora.family == "spectrum"
    cfg = HueCycleConfig.from_dict(aurora.effects["hue_cycle"])
    assert cfg.amplitude < 0.5, "aurora should stay in a narrower hue band than prism"
