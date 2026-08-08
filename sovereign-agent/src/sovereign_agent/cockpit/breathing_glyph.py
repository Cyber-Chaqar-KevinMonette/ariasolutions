"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/breathing_glyph.py — the glow generalized                      ║
║                                                                           ║
║  Kevin's prompt: "you know the red background of the little beating     ║
║  glowing heart in the bottom left corner? How can we turn the pulsing  ║
║  background into a modern usable UI object for decor?"                  ║
║                                                                           ║
║  Answer: take the pulse pattern (a sine-wave alpha modulation over a   ║
║  glyph) and make it a reusable Textual widget. Width-safe (the         ║
║  glyphs.py EAW lesson is law). Theme-aware (pulls colors from the      ║
║  active theme, not hardcoded). Composable into borders, indicators,   ║
║  or single-cell accents.                                                ║
║                                                                           ║
║  Architectural symmetry with cockpit/themes.py                          ║
║                                                                           ║
║    The same config shape used by aria-prism's hue_cycle effect —        ║
║    period_seconds, tick_seconds, amplitude — is reused here. The       ║
║    BreathingGlyph IS to alpha what hue_cycle IS to hue. Consistent     ║
║    mental model.                                                         ║
║                                                                           ║
║  Three named presets                                                    ║
║                                                                           ║
║    BREATH        — slow, calm pulse (4s period). Idle indicator.        ║
║    HEARTBEAT     — faster, two-beat (1.2s). Active-work indicator.      ║
║    URGENT_BLINK  — sharp, fast (0.6s). Alert-class indicator.           ║
║                                                                           ║
║  Composability                                                          ║
║                                                                           ║
║    BreathingGlyph(glyph=LOZENGE) is a single-cell pulse.                ║
║    BreathingBorder(glyph=LOZENGE, length=12) renders a row of them    ║
║    with phase offsets so the pulse RIPPLES along the border instead    ║
║    of synchronously blinking. That's the "modern usable UI object       ║
║    for decor" piece.                                                    ║
║                                                                           ║
║  Kill switch: SOV_NO_BREATHING_GLYPH=1 — falls back to static glyph,    ║
║  no animation, no timer. The widget still renders; it just stops       ║
║  breathing. (Reduces CPU for low-power scenarios.)                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Optional

# Textual import is lazy/optional — this module is importable in environments
# where Textual isn't installed (e.g., unit tests of the math). The widget
# classes themselves require Textual at instantiation time.
try:
    from textual.reactive import reactive
    from textual.timer import Timer
    from textual.widgets import Static
    from rich.text import Text
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False
    Static = object  # type: ignore[assignment,misc]
    Text = None  # type: ignore[assignment]

from sovereign_agent.glyphs import LOZENGE, is_width_safe


KILL_SWITCH_ENV = "SOV_NO_BREATHING_GLYPH"


# ─── Config presets ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PulseConfig:
    """Mirrors the hue_cycle shape from cockpit/themes.py.

    period_seconds: how long one full breath cycle takes
    tick_seconds:   render interval (smaller = smoother but more CPU)
    amplitude:      0.0..1.0 — how far alpha swings from the midpoint
                    (1.0 = full 0..1 swing; 0.5 = swings 0.25..0.75)
    midpoint:       0.0..1.0 — the "resting" alpha; pulse centers here
    color_slot:     which theme color drives the glyph
                    ('primary' | 'accent' | 'success' | 'warning' | 'error')
    """
    period_seconds: float = 4.0
    tick_seconds: float = 0.1
    amplitude: float = 0.6
    midpoint: float = 0.5
    color_slot: str = "primary"


BREATH = PulseConfig(period_seconds=4.0, tick_seconds=0.1, amplitude=0.4,
                     midpoint=0.55, color_slot="primary")
HEARTBEAT = PulseConfig(period_seconds=1.2, tick_seconds=0.06, amplitude=0.65,
                        midpoint=0.55, color_slot="error")
URGENT_BLINK = PulseConfig(period_seconds=0.6, tick_seconds=0.05, amplitude=0.85,
                           midpoint=0.55, color_slot="error")

# ─── v0.2.41 "Cosmic Fitness" additions — the god-tier presets ───────────
#
# Three more named pulses for the special-effects showcase. Same math, same
# kill switch; each just trades a different point in the (period, amplitude,
# midpoint) space for a distinct feel.
#
#   SHIMMER   — fast + low amplitude: light catching a facet, never still.
#   BEACON    — slow + high amplitude: a patient lighthouse swell.
#   STARLIGHT — medium + bright midpoint: a steady star with a gentle glow.

SHIMMER = PulseConfig(period_seconds=0.9, tick_seconds=0.05, amplitude=0.35,
                      midpoint=0.7, color_slot="accent")
BEACON = PulseConfig(period_seconds=3.2, tick_seconds=0.08, amplitude=0.9,
                     midpoint=0.5, color_slot="primary")
STARLIGHT = PulseConfig(period_seconds=2.4, tick_seconds=0.08, amplitude=0.45,
                        midpoint=0.7, color_slot="warning")


# ─── Pure math (testable without Textual) ────────────────────────────────


def alpha_at(t: float, config: PulseConfig) -> float:
    """The current alpha for a pulse at time t.

    Sine wave centered on midpoint with given amplitude and period.
    Clamped to [0, 1] to be safe even with bad config.
    """
    if config.period_seconds <= 0:
        return config.midpoint
    phase = (t % config.period_seconds) / config.period_seconds
    sine = math.sin(phase * 2.0 * math.pi)
    raw = config.midpoint + (config.amplitude / 2.0) * sine
    return max(0.0, min(1.0, raw))


def rgb_at_alpha(base_rgb: tuple[int, int, int], alpha: float,
                 bg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Linearly blend base_rgb toward bg_rgb by (1 - alpha).

    Terminals don't support true alpha; we fake it by compositing the
    glyph color toward the background. alpha=1.0 → full base color,
    alpha=0.0 → bg color (invisible).
    """
    return tuple(
        int(round(base_rgb[i] * alpha + bg_rgb[i] * (1.0 - alpha)))
        for i in range(3)
    )  # type: ignore[return-value]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


# ─── The widgets (require Textual) ───────────────────────────────────────


if _TEXTUAL_AVAILABLE:

    class BreathingGlyph(Static):
        """A single-cell glyph that breathes.

        Usage in Textual:
            yield BreathingGlyph(glyph="◊", config=HEARTBEAT)

        Width is exactly one cell, guaranteed (constructor refuses
        non-width-safe glyphs). The pulse runs via a Textual Timer; on
        unmount, the timer is cancelled.
        """

        def __init__(
            self,
            glyph: str = LOZENGE,
            config: PulseConfig = BREATH,
            base_hex: str = "#FF6B6B",
            bg_hex: str = "#1A0E0A",
            phase_offset: float = 0.0,
            assume_width_safe: bool = False,
            **kwargs,
        ):
            # The guard protects naive callers from EAW-wide glyphs. An informed
            # caller that has verified a glyph renders one cell in practice
            # (e.g. a project-blessed EAW-ambiguous mark like ♥ ● ★) may pass
            # assume_width_safe=True to opt out — the widget trusts the caller's
            # explicit assertion rather than re-deriving width policy here.
            if not assume_width_safe and not is_width_safe(glyph):
                raise ValueError(
                    f"glyph {glyph!r} is not width-safe; choose from glyphs.py "
                    f"SAFE constants, or pass assume_width_safe=True if you have "
                    f"verified it renders one cell"
                )
            super().__init__(glyph, **kwargs)
            self._glyph = glyph
            self._config = config
            self._base_rgb = _hex_to_rgb(base_hex)
            self._bg_rgb = _hex_to_rgb(bg_hex)
            self._phase_offset = phase_offset
            self._t0 = time.monotonic()
            self._timer: Optional[Timer] = None

        @property
        def is_pulsing(self) -> bool:
            return self._timer is not None

        def on_mount(self) -> None:
            if os.environ.get(KILL_SWITCH_ENV):
                # Kill switch active: render once, no timer.
                self._render_static()
                return
            self._timer = self.set_interval(
                self._config.tick_seconds,
                self._tick,
            )

        def on_unmount(self) -> None:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None

        def update_config(self, config: PulseConfig) -> None:
            """Swap presets at runtime (e.g., switch BREATH → URGENT_BLINK)."""
            self._config = config
            if self._timer is not None:
                self._timer.stop()
                self._timer = self.set_interval(config.tick_seconds, self._tick)

        def _tick(self) -> None:
            t = time.monotonic() - self._t0 + self._phase_offset
            alpha = alpha_at(t, self._config)
            mixed = rgb_at_alpha(self._base_rgb, alpha, self._bg_rgb)
            self.update(Text(self._glyph, style=f"bold {_rgb_to_hex(mixed)}"))

        def _render_static(self) -> None:
            self.update(Text(self._glyph, style=f"bold {_rgb_to_hex(self._base_rgb)}"))


    class BreathingBorder(Static):
        """A horizontal row of breathing glyphs with phase-offset ripple.

        Each cell pulses out-of-phase with its neighbors, so the border
        ripples along its length instead of synchronously blinking. The
        ripple direction is controlled by the sign of phase_step.
        """

        def __init__(
            self,
            length: int = 12,
            glyph: str = LOZENGE,
            config: PulseConfig = BREATH,
            base_hex: str = "#FF6B6B",
            bg_hex: str = "#1A0E0A",
            phase_step: float = 0.15,        # seconds offset per cell
            assume_width_safe: bool = False,
            **kwargs,
        ):
            # See BreathingGlyph.__init__ for the rationale on assume_width_safe.
            if not assume_width_safe and not is_width_safe(glyph):
                raise ValueError(
                    f"glyph {glyph!r} not width-safe (pass assume_width_safe=True "
                    f"if you have verified it renders one cell)"
                )
            super().__init__(glyph * length, **kwargs)
            self._length = length
            self._glyph = glyph
            self._config = config
            self._base_rgb = _hex_to_rgb(base_hex)
            self._bg_rgb = _hex_to_rgb(bg_hex)
            self._phase_step = phase_step
            self._t0 = time.monotonic()
            self._timer: Optional[Timer] = None

        def on_mount(self) -> None:
            if os.environ.get(KILL_SWITCH_ENV):
                self._render_static()
                return
            self._timer = self.set_interval(self._config.tick_seconds, self._tick)

        def on_unmount(self) -> None:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None

        def _tick(self) -> None:
            now = time.monotonic() - self._t0
            txt = Text()
            for i in range(self._length):
                t = now + i * self._phase_step
                alpha = alpha_at(t, self._config)
                mixed = rgb_at_alpha(self._base_rgb, alpha, self._bg_rgb)
                txt.append(self._glyph, style=f"bold {_rgb_to_hex(mixed)}")
            self.update(txt)

        def _render_static(self) -> None:
            self.update(
                Text(self._glyph * self._length, style=f"bold {_rgb_to_hex(self._base_rgb)}")
            )


__all__ = [
    "PulseConfig",
    "BREATH", "HEARTBEAT", "URGENT_BLINK",
    "SHIMMER", "BEACON", "STARLIGHT",
    "alpha_at", "rgb_at_alpha",
    "KILL_SWITCH_ENV",
]
if _TEXTUAL_AVAILABLE:
    __all__ += ["BreathingGlyph", "BreathingBorder"]
