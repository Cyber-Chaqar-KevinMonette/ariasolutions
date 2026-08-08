"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/hue_cycle.py — smooth spectrum cycling for special themes      ║
║                                                                           ║
║  When a theme opts in via its effects slot, this engine rotates a       ║
║  subset of color slots around the color wheel — keeping background/      ║
║  surface/panel stable for readability, and breathing the accents.       ║
║                                                                           ║
║  Design choices:                                                         ║
║                                                                           ║
║    • Conservative defaults — 240s per full rotation, 2s tick. Ambient   ║
║      not strobing. The eye won't see motion frame-to-frame; you'll just ║
║      look up after a minute and notice the colors have drifted.         ║
║                                                                           ║
║    • Hue-only rotation. Saturation and lightness stay fixed at each      ║
║      slot's original values, so a punchy primary stays punchy as it     ║
║      moves through the wheel — only the hue changes.                    ║
║                                                                           ║
║    • Semantic colors (success/warning/error) DO NOT cycle. Green must  ║
║      stay green; red must stay red. Article I — no silent degradation:  ║
║      we don't break semantic associations for aesthetics.               ║
║                                                                           ║
║    • Fail-safe. Any tick that raises an exception stops the engine     ║
║      cleanly. The cockpit never crashes from cycling.                   ║
║                                                                           ║
║    • Kill switch. Setting SOV_NO_HUE_CYCLE=1 in the environment        ║
║      disables cycling regardless of theme config. For migraine days,    ║
║      streaming setups, screen recordings, or when cycling feels        ║
║      distracting.                                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import colorsys
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .themes import CockpitTheme, get_theme_by_name

if TYPE_CHECKING:
    from textual.app import App


KILL_SWITCH_ENV = "SOV_NO_HUE_CYCLE"

# Slots that may rotate through the spectrum
DEFAULT_ROTATABLE_SLOTS = ("primary", "accent", "secondary")
# ALWAYS locked: text + semantic colours (readability + "green stays green",
# "error stays red"). These never rotate, regardless of any theme config.
HARD_NEVER_ROTATE_SLOTS = frozenset({
    "foreground", "success", "warning", "error",
})
# Structural surfaces: locked BY DEFAULT, but a theme may opt in to rotating
# them via effects.hue_cycle.allow_background — kept dark by a lightness cap so
# the background drifts in hue while staying a pleasant near-black tint.
STRUCTURAL_SLOTS = frozenset({"background", "surface", "panel"})
# Back-compat: the historical union. Without the opt-in, this is the lock set.
NEVER_ROTATE_SLOTS = HARD_NEVER_ROTATE_SLOTS | STRUCTURAL_SLOTS


@dataclass
class HueCycleConfig:
    """Parsed config from a CockpitTheme.effects['hue_cycle'] dict.

    slot_speeds: per-slot rotation multipliers. A speed of 1.0 means one
    full hue revolution per `period_seconds`. 0.5 = half-speed; -1.0 =
    full-speed in the opposite direction. Different slots moving at
    different rates is what makes the prism feel like light through
    glass instead of a sterile color wheel.
    """
    period_seconds: float = 240.0   # full rotation at speed=1.0
    tick_seconds: float = 2.0       # refresh frame interval
    amplitude: float = 1.0          # 0 = no cycling; 1 = full hue range
    rotate_slots: tuple[str, ...] = DEFAULT_ROTATABLE_SLOTS
    slot_speeds: dict = field(default_factory=dict)  # slot → speed multiplier
    allow_background: bool = False   # opt in to rotating background/surface/panel
    dark_cap: float = 0.16           # max lightness for rotated structural slots

    @classmethod
    def from_dict(cls, d: dict) -> "HueCycleConfig":
        slots = d.get("rotate_slots", DEFAULT_ROTATABLE_SLOTS)
        allow_bg = bool(d.get("allow_background", False))
        # When background rotation is opted-in, only the hard set stays locked;
        # otherwise structural surfaces are locked too (historical behaviour).
        locked = HARD_NEVER_ROTATE_SLOTS if allow_bg else NEVER_ROTATE_SLOTS
        safe_slots = tuple(s for s in slots if s not in locked)
        speeds = d.get("slot_speeds", {})
        # Defense-in-depth: ignore speed entries for locked slots.
        safe_speeds = {k: float(v) for k, v in speeds.items()
                       if k not in locked}
        return cls(
            period_seconds=max(10.0, float(d.get("period_seconds", 240.0))),
            tick_seconds=max(0.5, float(d.get("tick_seconds", 2.0))),
            amplitude=max(0.0, min(1.0, float(d.get("amplitude", 1.0)))),
            rotate_slots=safe_slots or DEFAULT_ROTATABLE_SLOTS,
            slot_speeds=safe_speeds,
            allow_background=allow_bg,
            dark_cap=max(0.0, min(0.5, float(d.get("background_max_lightness", 0.16)))),
        )

    def speed_for(self, slot: str) -> float:
        """Per-slot speed multiplier. Defaults to 1.0 if not specified."""
        return self.slot_speeds.get(slot, 1.0)


# ─── Color math ───────────────────────────────────────────────────────────


def _hex_to_hls(hex_str: str) -> tuple[float, float, float]:
    """'#FF6B9D' → (hue, lightness, saturation) in 0..1."""
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    return colorsys.rgb_to_hls(r, g, b)


def _hls_to_hex(h: float, l: float, s: float) -> str:
    """(hue, lightness, saturation) in 0..1 → '#RRGGBB'."""
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return "#{:02X}{:02X}{:02X}".format(
        int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
    )


def rotated_color(original_hex: str, hue_offset: float,
                  max_lightness: float | None = None) -> str:
    """Shift a color's hue by hue_offset (0..1 = full wheel). Saturation is
    preserved; lightness is preserved too, unless `max_lightness` is given —
    then it's capped (used for structural slots so a rotating background stays
    a dark, pleasant tint rather than strobing bright)."""
    h, l, s = _hex_to_hls(original_hex)
    if max_lightness is not None:
        l = min(l, max_lightness)
    return _hls_to_hex(h + hue_offset, l, s)


def build_phase_theme(base: CockpitTheme, config: HueCycleConfig,
                      phase: float) -> CockpitTheme:
    """Return a new CockpitTheme with rotatable slots shifted by `phase`.

    phase is a value in [0, 1] representing position around the color wheel.
    Each slot's rotation is scaled by its per-slot speed (config.speed_for),
    so different slots can move at different rates and even opposite
    directions. This is what gives aria-prism its prismatic quality —
    primary, accent, and secondary trace different orbits around the wheel,
    so the cockpit feels alive rather than uniformly rotating.

    Semantic and text slots (foreground, success/warning/error) are NEVER
    touched. Structural surfaces (background/surface/panel) are touched only
    when the theme opted in (allow_background), and then with a lightness cap so
    they stay dark.
    """
    from dataclasses import replace
    locked = (HARD_NEVER_ROTATE_SLOTS if config.allow_background
              else NEVER_ROTATE_SLOTS)
    new_values = {}
    for slot in config.rotate_slots:
        if slot in locked:
            continue
        current = getattr(base, slot, None)
        if not current:
            continue
        slot_offset = phase * config.amplitude * config.speed_for(slot)
        if slot in STRUCTURAL_SLOTS:
            new_values[slot] = rotated_color(current, slot_offset,
                                             max_lightness=config.dark_cap)
        else:
            new_values[slot] = rotated_color(current, slot_offset)
    return replace(base, **new_values)


# ─── The engine ───────────────────────────────────────────────────────────


class HueCycleEngine:
    """Drives smooth hue cycling for a single registered theme.

    Lifecycle:
      engine = HueCycleEngine(app, "aria-prism", config)
      engine.start()    # begins ticking
      engine.stop()     # halts cleanly; theme stays at last frame
    """

    def __init__(self, app: "App", theme_name: str, config: HueCycleConfig):
        self.app = app
        self.theme_name = theme_name
        self.config = config
        self._elapsed = 0.0
        self._timer = None
        self._base: CockpitTheme | None = None
        self._running = False

    def start(self) -> bool:
        """Begin cycling. Returns False if disabled (kill switch) or unable."""
        if os.environ.get(KILL_SWITCH_ENV):
            return False
        self._base = get_theme_by_name(self.theme_name)
        if self._base is None:
            return False
        try:
            self._timer = self.app.set_interval(
                self.config.tick_seconds, self._tick
            )
            self._running = True
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Halt cycling. Last frame remains applied."""
        self._running = False
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None

    def _tick(self) -> None:
        """One frame. Compute next hue, build a theme, re-register, force refresh.

        The non-obvious part: Textual's `theme` is a reactive str. When we
        re-register a theme with the SAME name, setting `self.app.theme =
        name` is a no-op because the reactive sees no change. So we
        manually invoke the parts of `_watch_theme` that actually apply
        the new colors: invalidate the CSS cache, then re-run css refresh.

        Fail-safe: any exception here stops the engine. Cockpit survives.
        """
        try:
            if not self._running or self._base is None:
                return
            self._elapsed += self.config.tick_seconds
            phase = (self._elapsed / self.config.period_seconds) % 1.0
            new_theme = build_phase_theme(self._base, self.config, phase)
            # Re-register under the same name (overwrites previous entry)
            self.app.register_theme(new_theme.to_textual_theme())
            # Force Textual to re-apply, since the theme name didn't change.
            # This mirrors what _watch_theme does internally on a real theme change.
            if hasattr(self.app, "_invalidate_css"):
                self.app._invalidate_css()
            if hasattr(self.app, "refresh_css"):
                self.app.refresh_css(animate=False)
        except Exception:
            # Fail-safe: stop cleanly, don't crash the cockpit
            self.stop()


# ─── Wiring helpers ───────────────────────────────────────────────────────


def maybe_start_for_active_theme(app: "App", active_theme_name: str | None) -> HueCycleEngine | None:
    """If the active theme has hue_cycle effects configured, start an engine.

    Returns the engine (so the caller can stop it) or None.
    """
    if not active_theme_name:
        return None
    theme = get_theme_by_name(active_theme_name)
    if theme is None or not theme.effects:
        return None
    cycle_cfg = theme.effects.get("hue_cycle")
    if not isinstance(cycle_cfg, dict):
        return None
    config = HueCycleConfig.from_dict(cycle_cfg)
    engine = HueCycleEngine(app, active_theme_name, config)
    if engine.start():
        return engine
    return None


__all__ = [
    "HueCycleConfig",
    "HueCycleEngine",
    "KILL_SWITCH_ENV",
    "DEFAULT_ROTATABLE_SLOTS",
    "NEVER_ROTATE_SLOTS",
    "rotated_color",
    "build_phase_theme",
    "maybe_start_for_active_theme",
]
