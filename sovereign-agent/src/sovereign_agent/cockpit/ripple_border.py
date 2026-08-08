"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/ripple_border.py — the glow, sent travelling around a frame       ║
║                                                                            ║
║  breathing_glyph.py taught a single glyph (and a single ROW of glyphs) to  ║
║  pulse: a sine-wave alpha modulation, faked over a terminal by blending a  ║
║  base colour toward the background. BreathingBorder ripples that pulse     ║
║  along ONE horizontal line by phase-offsetting each cell.                  ║
║                                                                            ║
║  This module generalizes that idea to a full RECTANGLE perimeter. The      ║
║  whole frame is parametrized as a single distance `d` that walks the       ║
║  outline — top L→R, right T→B, bottom R→L, left B→T — and a travelling     ║
║  wave `sin(2π·(d − speed·t)/wavelen)` sets each cell's brightness. The      ║
║  crest sweeps smoothly around all four sides and through the corners,      ║
║  so the border looks alive without ever breaking into "marching ants":     ║
║  the trough is tuned to stay clearly visible, so the frame always reads    ║
║  as a complete border with a glow gliding around it.                       ║
║                                                                            ║
║  WHY CUSTOM-RENDERED (not CSS)                                             ║
║    A Textual CSS border is a single colour. Even per-edge colours give     ║
║    only a coarse 4-segment sweep. A true per-cell wave needs us to paint   ║
║    the frame ourselves — so RippleFrame sets `border: none; padding: 1`    ║
║    (reserving a one-cell ring) and overrides `render_lines` to draw the    ║
║    rounded box-drawing frame on the OUTER ring while children composite     ║
║    over the interior, untouched.                                           ║
║                                                                            ║
║  WIDTH LAW                                                                  ║
║    The frame glyphs are the same round box-drawing characters Textual's     ║
║    own `border: round` uses (╭ ╮ ╰ ╯ ─ │). They are EAW-ambiguous but      ║
║    project-blessed "convention" tier — exactly the chrome already on        ║
║    every pane — so this introduces no new width risk.                      ║
║                                                                            ║
║  THEME-AWARE                                                                ║
║    Colours are resolved from the live theme at mount (primary for the      ║
║    glow, surface for the trough it fades into), so the frame matches        ║
║    whatever theme is active and re-resolves on theme change.               ║
║                                                                            ║
║  REDUCED MOTION / KILL SWITCHES                                            ║
║    SOV_NO_RIPPLE_BORDER=1   — frame renders once, static, no timer.        ║
║    SOV_REDUCED_MOTION=1     — same (shared motion-sensitivity switch).     ║
║    SOV_NO_GLYPH_ANIMATION=1 — same.                                         ║
║    A static frame is held at the wave midpoint, so the border is still      ║
║    fully drawn — it simply stops moving.                                    ║
║                                                                            ║
║  This module imports cleanly without Textual (the pure maths are usable     ║
║  in tests); the widget is only defined when Textual is importable,          ║
║  mirroring breathing_glyph.py / glyph_stage.py.                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, replace

# Kill switches. The dedicated one plus the two shared motion switches honored
# elsewhere in the cockpit (animated_glyph.py), so "reduce motion" is one flip.
RIPPLE_KILL_SWITCH_ENV = "SOV_NO_RIPPLE_BORDER"
REDUCED_MOTION_ENV = "SOV_REDUCED_MOTION"
ANIM_KILL_SWITCH_ENV = "SOV_NO_GLYPH_ANIMATION"

# Round-border glyphs — identical to Textual's `border: round`. Convention-tier
# (EAW-ambiguous but project-blessed; the same chrome already on every pane).
ARC_TL, ARC_TR, ARC_BL, ARC_BR = "\u256d", "\u256e", "\u2570", "\u256f"  # ╭ ╮ ╰ ╯
EDGE_H, EDGE_V = "\u2500", "\u2502"  # ─ │

# Sensible colour fallbacks if a theme leaves a slot unset (stock Textual
# themes don't define surface/panel; the cockpit's own themes do).
_FALLBACK_BASE = "#A78BFA"   # soft violet glow
_FALLBACK_BG = "#0E0B14"     # near-black surface to fade into

__all__ = [
    "RIPPLE_KILL_SWITCH_ENV",
    "REDUCED_MOTION_ENV",
    "ANIM_KILL_SWITCH_ENV",
    "ARC_TL", "ARC_TR", "ARC_BL", "ARC_BR", "EDGE_H", "EDGE_V",
    "RippleParams",
    "RIPPLE_IDLE", "RIPPLE_BUSY", "RIPPLE_NEWS", "RIPPLE_HALT", "RIPPLE_STAGE",
    "RIPPLE_AURORA",
    "ripple_motion_disabled",
    "perimeter_distance_count",
    "perimeter_alpha",
    "perimeter_hue",
    "perimeter_cell_distance",
    "ripple_cell_rgb",
    "merge_ripple_params",
    "hex_to_rgb", "rgb_to_hex", "blend_rgb", "hue_to_rgb",
]


# ── Tunable wave shapes ──────────────────────────────────────────────────
#
# A point on the perimeter completes one brightness cycle every wavelen/speed
# seconds; `amplitude`/`midpoint` set how far it swings and where it rests.
# Defaults keep the trough visible (the frame never vanishes) — a glow gliding
# around a solid border, "alive but not chaotic", per Kevin's "without making
# it look weird".


@dataclass(frozen=True)
class RippleParams:
    """One named feel for a rippling frame.

    wavelen:   cells per wave (longer = fewer, broader crests).
    speed:     cells/second the crest travels around the perimeter.
    amplitude: 0..1 — how far brightness swings from the midpoint.
    midpoint:  0..1 — the resting brightness; the wave centres here.
    color_slot:which theme colour drives the glow ('primary' | 'accent'
               | 'secondary' | 'error' | 'success' | 'warning').
    """
    wavelen: float = 52.0
    speed: float = 22.0
    amplitude: float = 0.6
    midpoint: float = 0.62
    color_slot: str = "primary"
    # ── Aurora mode: a smooth hue cycle layered ON TOP of the ripple ──────
    # When hue_cycle is True, the glow's *hue* is generated (not taken from the
    # theme slot): a full spectrum is spread around the perimeter and rotates
    # over time, while the brightness wave above still travels around. The
    # result is a rainbow border that ripples — "aurora + ripple at once".
    hue_cycle: bool = False
    hue_period: float = 12.0   # seconds for one full rotation of the spectrum
    hue_spread: float = 1.0    # how many full rainbows wrap the perimeter (1 = one)
    hue_start: float = 0.0     # starting hue offset, [0,1)
    saturation: float = 0.62   # HSV saturation for the generated hue
    value: float = 0.97        # HSV value (brightness) before the ripple wave


# The cockpit's four moods for the main outer frame, plus a livelier preset for
# the small GlyphStage. The breathing worker swaps between idle/busy; news and
# halt are mood signals (§30) the frame can show on demand.
RIPPLE_IDLE = RippleParams(wavelen=52.0, speed=16.0, amplitude=0.55,
                           midpoint=0.54, color_slot="primary")
RIPPLE_BUSY = RippleParams(wavelen=40.0, speed=40.0, amplitude=0.72,
                           midpoint=0.58, color_slot="accent")
RIPPLE_NEWS = RippleParams(wavelen=46.0, speed=30.0, amplitude=0.68,
                           midpoint=0.60, color_slot="accent")
RIPPLE_HALT = RippleParams(wavelen=30.0, speed=52.0, amplitude=0.85,
                           midpoint=0.55, color_slot="error")
# Smaller perimeter → a shorter wavelength reads better on a GlyphStage.
RIPPLE_STAGE = RippleParams(wavelen=26.0, speed=15.0, amplitude=0.70,
                            midpoint=0.60, color_slot="secondary")
# The Aurora frame: a full spectrum wrapped around the border, rotating slowly
# (the GlyphStage aurora glyph's hue-cycle, made into a frame) WHILE a gentle
# brightness glow ripples around it. Theme-independent rainbow. Tuned for a
# SMOOTH, natural glide: a broad wavelength + slow speed keep the gradient
# gentle, and a low resting trough lets the border melt toward the surface
# between glow passes (so it reads as a faint, clearly-coloured edge, not pale
# near-white lines).
RIPPLE_AURORA = RippleParams(
    wavelen=56.0, speed=14.0, amplitude=0.58, midpoint=0.42,
    color_slot="primary",          # fallback only; ignored while hue_cycle is on
    hue_cycle=True, hue_period=12.0, hue_spread=1.0, hue_start=0.0,
    saturation=0.84, value=0.92,
)


def merge_ripple_params(base: RippleParams, override) -> RippleParams:
    """Overlay a (partial) per-theme ripple dict onto a base preset.

    `override` is a theme's ``effects['ripple']`` dict — any of
    wavelen / speed / amplitude / midpoint / color_slot, plus the Aurora-mode
    keys hue_cycle / hue_period / hue_spread / hue_start / saturation / value.
    So a theme (curated OR a hand-written custom JSON) can say e.g.
    ``"ripple": {"hue_cycle": true, "hue_period": 10}`` to get a rainbow frame.
    Unknown or malformed keys are ignored — a bad theme can't crash the frame.
    Returns `base` unchanged when there's nothing valid to apply.
    """
    if not isinstance(override, dict) or not override:
        return base
    kw: dict = {}
    for k in ("wavelen", "speed", "amplitude", "midpoint",
              "hue_period", "hue_spread", "hue_start", "saturation", "value"):
        if k in override:
            try:
                kw[k] = float(override[k])
            except (TypeError, ValueError):
                pass
    if "hue_cycle" in override:
        kw["hue_cycle"] = bool(override["hue_cycle"])
    slot = override.get("color_slot")
    if isinstance(slot, str) and slot:
        kw["color_slot"] = slot
    return replace(base, **kw) if kw else base


def ripple_motion_disabled() -> bool:
    """True if any kill switch or reduced-motion flag is set."""
    return bool(
        os.environ.get(RIPPLE_KILL_SWITCH_ENV)
        or os.environ.get(REDUCED_MOTION_ENV)
        or os.environ.get(ANIM_KILL_SWITCH_ENV)
    )


# ── Pure maths (testable without Textual) ────────────────────────────────


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def blend_rgb(base: tuple[int, int, int], bg: tuple[int, int, int],
              alpha: float) -> tuple[int, int, int]:
    """Fake alpha: blend `base` toward `bg`. alpha=1 → base, alpha=0 → bg."""
    a = max(0.0, min(1.0, alpha))
    return tuple(int(round(bg[i] + (base[i] - bg[i]) * a)) for i in range(3))  # type: ignore[return-value]


def hue_to_rgb(hue: float, sat: float = 0.62, val: float = 0.97) -> tuple[int, int, int]:
    """HSV→RGB (0..255). `hue` wraps mod 1.0; sat/val clamped to [0,1]."""
    import colorsys
    h = hue - math.floor(hue)  # wrap into [0,1)
    s = max(0.0, min(1.0, sat))
    v = max(0.0, min(1.0, val))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def perimeter_hue(d: float, elapsed: float, perimeter: int,
                  params: RippleParams) -> float:
    """The (wrapped) hue for a perimeter cell at distance `d`, time `elapsed`.

    Spreads `hue_spread` full rainbows around the outline and rotates the whole
    spectrum once per `hue_period` seconds. Returns a value in [0,1).
    """
    pos = (params.hue_spread * (d / perimeter)) if perimeter > 0 else 0.0
    spin = (elapsed / params.hue_period) if params.hue_period > 0 else 0.0
    hue = params.hue_start + pos + spin
    return hue - math.floor(hue)


def perimeter_cell_distance(x: int, y: int, w: int, h: int) -> float | None:
    """Walk-distance `d` of the border cell at (x, y) in a w×h frame, matching
    `ripple_frame_strips`' parametrization (top L→R, right T→B, bottom R→L,
    left B→T). Returns None for interior (non-border) cells."""
    if y == 0:
        return float(x)                       # top edge
    if y == h - 1:
        return float(w + h + (w - 1 - x))     # bottom edge (R→L)
    if x == w - 1:
        return float(w + y)                   # right edge (T→B)
    if x == 0:
        return float(2 * w + h + (h - 1 - y)) # left edge (B→T)
    return None


def ripple_cell_rgb(d: float, elapsed: float, perimeter: int,
                    base_rgb: tuple[int, int, int],
                    bg_rgb: tuple[int, int, int],
                    params: RippleParams) -> tuple[int, int, int]:
    """The colour of one frame cell at distance `d`: the travelling-wave glow,
    rainbow (aurora) or theme-coloured, blended toward the background. Shared by
    `ripple_frame_strips` and the border-recolour mixin so they always agree."""
    a = perimeter_alpha(d, elapsed, params)
    if params.hue_cycle:
        base = hue_to_rgb(perimeter_hue(d, elapsed, perimeter, params),
                          params.saturation, params.value)
    else:
        base = base_rgb
    return blend_rgb(base, bg_rgb, a)


def perimeter_distance_count(outer_w: int, outer_h: int) -> int:
    """Total perimeter length in cells used by the parametrization.

    The walk covers top (w) + right (h) + bottom (w) + left (h). Corner cells
    are counted once (as the start of the top/bottom edges), matching the
    distance assignment in `perimeter_alpha` / the strip renderer.
    """
    return 2 * outer_w + 2 * outer_h


def perimeter_alpha(d: float, elapsed: float, params: RippleParams) -> float:
    """Brightness in [0,1] for a perimeter cell at distance `d`, time `elapsed`.

    A travelling wave: phase advances with `d` and recedes with time, so the
    crest sweeps around the outline. Clamped to a valid range.
    """
    if params.wavelen <= 0:
        return max(0.0, min(1.0, params.midpoint))
    phase = (d - params.speed * elapsed) / params.wavelen
    val = params.midpoint + params.amplitude * 0.5 * math.sin(2 * math.pi * phase)
    return max(0.0, min(1.0, val))


# ── The renderer + widget (require Textual) ──────────────────────────────

try:  # pragma: no cover - exercised only when Textual is present
    from rich.segment import Segment
    from rich.style import Style
    from textual.color import Color
    from textual.containers import Horizontal
    from textual.geometry import Region
    from textual.strip import Strip

    def _rgb_style(fg: tuple[int, int, int] | None,
                   bg: tuple[int, int, int]) -> Style:
        bgc = f"rgb({bg[0]},{bg[1]},{bg[2]})"
        if fg is None:
            return Style(bgcolor=bgc)
        return Style(color=f"rgb({fg[0]},{fg[1]},{fg[2]})", bgcolor=bgc, bold=True)

    def _title_cells(title: str, outer_w: int) -> dict[int, str]:
        """Map x-column → title character for a left-aligned border title.

        Mirrors Textual's `╭─ Title ──…─╮`: corner, one edge dash, then a
        space-padded label, then dashes to the far corner. Truncated to fit.
        Returns only the columns the *label text* occupies (the surrounding
        dashes stay part of the rippling top edge).
        """
        if not title:
            return {}
        label = f" {title} "
        start = 2  # after ╭─
        # Need room for: ╭ ─ <label> ─ ╮  → start + len + 2 (one dash + corner)
        max_len = outer_w - start - 2
        if max_len < 1:
            return {}
        if len(label) > max_len:
            label = label[: max(1, max_len)]
        return {start + i: ch for i, ch in enumerate(label)}

    def ripple_frame_strips(
        outer_w: int,
        outer_h: int,
        elapsed: float,
        base_rgb: tuple[int, int, int],
        bg_rgb: tuple[int, int, int],
        crop: "Region",
        params: RippleParams,
        *,
        title: str | None = None,
        title_rgb: tuple[int, int, int] | None = None,
        fill_interior: bool = True,
    ) -> "list[Strip]":
        """Render a rippling rounded frame as a list of Strips for `crop`.

        Draws the full outer ring (rows 0 & h-1, cols 0 & w-1) with a per-cell
        travelling-wave glow, fills the interior with the background colour
        (children composite over it), optionally paints a left-aligned title
        into the top edge, then crops to the visible region.

        The coordinate contract (verified): `crop` is the widget's full OUTER
        region, so the caller passes `self.outer_size` dimensions; children are
        inset by the widget's padding and drawn by the compositor on top.
        """
        w, h = outer_w, outer_h
        bg_style = _rgb_style(None, bg_rgb)
        if w < 2 or h < 2:
            return [Strip.blank(crop.width, bg_style)] * crop.height

        title_map = _title_cells(title, w) if title else {}

        # Aurora mode: the glow hue is generated (rainbow around the perimeter,
        # rotating over time) instead of taken from base_rgb; the ripple wave
        # still modulates brightness on top. Otherwise: theme-coloured glow.
        perimeter = perimeter_distance_count(w, h)

        def cell_rgb(d: float) -> tuple[int, int, int]:
            a = perimeter_alpha(d, elapsed, params)
            if params.hue_cycle:
                hue = perimeter_hue(d, elapsed, perimeter, params)
                base = hue_to_rgb(hue, params.saturation, params.value)
                return blend_rgb(base, bg_rgb, a)
            return blend_rgb(base_rgb, bg_rgb, a)

        def edge_style(d: float) -> Style:
            return _rgb_style(cell_rgb(d), bg_rgb)

        # Title hue: track the top-left of the rainbow in aurora mode, else base.
        if params.hue_cycle:
            t_rgb = hue_to_rgb(perimeter_hue(2, elapsed, perimeter, params),
                               params.saturation, params.value)
        else:
            t_rgb = title_rgb if title_rgb is not None else base_rgb
        title_style = _rgb_style(t_rgb, bg_rgb)

        top_n, right_n, bot_n = w, h, w  # distance offsets per edge
        rows: list[Strip] = []
        for y in range(h):
            if y == 0:
                segs = []
                for x in range(w):
                    if x in title_map:
                        segs.append(Segment(title_map[x], title_style))
                        continue
                    g = ARC_TL if x == 0 else (ARC_TR if x == w - 1 else EDGE_H)
                    segs.append(Segment(g, edge_style(x)))
                rows.append(Strip(list(Segment.simplify(segs)), w))
            elif y == h - 1:
                segs = []
                for x in range(w):
                    g = ARC_BL if x == 0 else (ARC_BR if x == w - 1 else EDGE_H)
                    segs.append(Segment(g, edge_style(top_n + right_n + (w - 1 - x))))
                rows.append(Strip(list(Segment.simplify(segs)), w))
            else:
                d_left = top_n + right_n + bot_n + (h - 1 - y)
                d_right = top_n + y
                segs = [Segment(EDGE_V, edge_style(d_left))]
                if w > 2:
                    if fill_interior:
                        segs.append(Segment(" " * (w - 2), bg_style))
                    else:
                        # Transparent interior: a no-op single space run keeps
                        # the Strip width correct while letting lower layers show.
                        segs.append(Segment(" " * (w - 2), Style()))
                if w > 1:
                    segs.append(Segment(EDGE_V, edge_style(d_right)))
                rows.append(Strip(list(Segment.simplify(segs)), w))

        out: list[Strip] = []
        for i in range(crop.height):
            yy = crop.y + i
            if 0 <= yy < len(rows):
                out.append(rows[yy].crop(crop.x, crop.x + crop.width))
            else:
                out.append(Strip.blank(crop.width, bg_style))
        return out

    def resolve_theme_rgb(app, *slots: str,
                          fallback: str) -> tuple[int, int, int]:
        """Resolve the first available theme colour slot to an RGB tuple.

        Tries the live theme's named slots in order; falls back to `fallback`
        if none resolve (stock themes leave surface/panel unset).
        """
        theme = None
        try:
            theme = app.current_theme
        except Exception:  # noqa: BLE001
            try:
                theme = app.get_theme(app.theme)
            except Exception:  # noqa: BLE001
                theme = None
        if theme is not None:
            for slot in slots:
                val = getattr(theme, slot, None)
                if val:
                    try:
                        return hex_to_rgb(Color.parse(val).hex)
                    except Exception:  # noqa: BLE001
                        continue
        return hex_to_rgb(fallback)

    class RippleFrame(Horizontal):
        """A horizontal container whose rounded border ripples with a glow.

        Drop-in for the main `#main` Horizontal: same layout (children laid out
        left-to-right), but the border is custom-rendered so a glow sweeps
        around the whole perimeter. Use `set_mode()` to switch the feel
        (idle / busy / news / halt); the colour is resolved from the live theme.

        CSS contract: `border: none; padding: 1`. The padding reserves the
        one-cell ring the frame is painted into; children sit inside it.
        """

        DEFAULT_CSS = """
        RippleFrame {
            height: 1fr;
            border: none;
            padding: 1;
            background: $surface;
        }
        """

        def __init__(
            self,
            *children,
            params: RippleParams = RIPPLE_IDLE,
            base_slot_fallback: str = _FALLBACK_BASE,
            bg_slot_fallback: str = _FALLBACK_BG,
            # anti-lag-d: 0.06 (16.7fps) → 0.1 (10fps). The glow sweep is a
            # slow travelling wave; 10fps is visually indistinguishable for
            # it and cuts this always-on render loop's call rate by 40%.
            tick_seconds: float = 0.1,
            **kwargs,
        ) -> None:
            super().__init__(*children, **kwargs)
            self._idle_params = params      # the idle baseline (constructor arg)
            self._mode = "idle"             # idle | busy | news | halt
            self._base_fallback = base_slot_fallback
            self._bg_fallback = bg_slot_fallback
            self._tick = tick_seconds
            self._t0 = time.monotonic()
            self._timer = None
            self._eff = params              # effective params = mode ⊕ theme tuning
            self._base_rgb = hex_to_rgb(base_slot_fallback)
            self._bg_rgb = hex_to_rgb(bg_slot_fallback)

        # ── mode + per-theme tuning ──
        def _mode_preset(self, mode: str) -> RippleParams:
            return {
                "idle": self._idle_params,
                "busy": RIPPLE_BUSY,
                "news": RIPPLE_NEWS,
                "halt": RIPPLE_HALT,
                "aurora": RIPPLE_AURORA,
            }.get(mode, self._idle_params)

        def _theme_ripple_override(self) -> dict:
            """The active theme's ``effects['ripple']`` tuning, or {}.

            Prefers an app-provided resolver (so it covers BOTH curated and
            user/custom themes); falls back to the curated catalog by name.
            Never raises — a bad theme can't break the frame.
            """
            getter = getattr(self.app, "active_ripple_effects", None)
            if callable(getter):
                try:
                    d = getter()
                    if isinstance(d, dict):
                        return d
                except Exception:  # noqa: BLE001
                    pass
            try:
                from .themes import get_theme_by_name
                spec = get_theme_by_name(getattr(self.app, "theme", "") or "")
                if spec is not None and isinstance(getattr(spec, "effects", None), dict):
                    r = spec.effects.get("ripple")
                    if isinstance(r, dict):
                        return r
            except Exception:  # noqa: BLE001
                pass
            return {}

        def _compute_effective(self) -> None:
            params = merge_ripple_params(self._mode_preset(self._mode),
                                         self._theme_ripple_override())
            # Halt is a safety signal — always the error hue, regardless of any
            # theme tuning, so an alarm reads as an alarm in every theme.
            if self._mode == "halt":
                params = replace(params, color_slot="error")
            self._eff = params

        def _resolve_colors(self) -> None:
            """Resolve glow + trough from the LIVE theme.

            anti-lag-d: memoized on the live theme OBJECT's identity. The
            hue-cycle engine re-registers a NEW theme object (same name)
            every few seconds and stock theme switches replace it too — so
            identity is exactly the right cache key: re-parse when the
            object changes, skip the ~17-per-second re-parses in between.
            (Before this, both always-on ripple widgets re-ran Rich
            Color.parse() every frame, all session, for values that only
            actually change every few seconds at most.)"""
            try:
                theme_obj = self.app.current_theme
            except Exception:  # noqa: BLE001
                theme_obj = None
            # Key on (theme identity, effective color_slot): a mode change
            # (idle→busy→halt) swaps the slot without swapping the theme
            # object, so the slot must be part of the key or a mode switch
            # would render with the stale color.
            key = (id(theme_obj), self._eff.color_slot)
            if getattr(self, "_colors_key", None) == key and theme_obj is not None:
                return
            self._colors_key = key
            self._base_rgb = resolve_theme_rgb(
                self.app, self._eff.color_slot, fallback=self._base_fallback
            )
            self._bg_rgb = resolve_theme_rgb(
                self.app, "surface", "panel", "background",
                fallback=self._bg_fallback,
            )

        # ── lifecycle ──
        def on_mount(self) -> None:
            self._compute_effective()
            self._resolve_colors()
            # React to theme switches: re-derive tuning + repaint immediately.
            # (Covers the reduced-motion/static case, where there's no timer.)
            try:
                self.app.theme_changed_signal.subscribe(self, self._on_theme_changed)
            except Exception:  # noqa: BLE001
                pass
            if ripple_motion_disabled():
                self.refresh()   # static frame, no timer
                return
            self._timer = self.set_interval(self._tick, self.refresh)

        def _on_theme_changed(self, *_args) -> None:
            self._compute_effective()
            self._resolve_colors()
            self.refresh()

        def on_unmount(self) -> None:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None

        # ── public API ──
        def set_params(self, params: RippleParams) -> None:
            """Replace the idle baseline wave shape + slot, and show it now."""
            self._idle_params = params
            self._mode = "idle"
            self._compute_effective()
            self._resolve_colors()
            self.refresh()

        def set_mode(self, mode: str) -> None:
            """Switch feel by name: 'idle' | 'busy' | 'news' | 'halt' | 'aurora'.

            'aurora' is the rainbow ripple — a full spectrum wrapped around the
            border, rotating over time, with the glow still rippling on top.
            """
            self._mode = mode if mode in ("idle", "busy", "news", "halt", "aurora") else "idle"
            self._compute_effective()
            self._resolve_colors()
            self.refresh()

        # ── rendering ──
        def render_lines(self, crop: "Region") -> "list[Strip]":
            size = self.outer_size
            # Resolve the colour every frame so the border follows theme changes
            # AND live hue-cycling themes (aria-prism / aurora / nebula). It's a
            # dict lookup + hex parse — trivial at ~17fps.
            self._resolve_colors()
            # When motion is disabled, freeze at t=0 so the frame holds a clean
            # static wave (still fully drawn — it just stops moving).
            now = 0.0 if ripple_motion_disabled() else (time.monotonic() - self._t0)
            return ripple_frame_strips(
                size.width, size.height, now,
                self._base_rgb, self._bg_rgb, crop, self._eff,
            )

    from rich.cells import cell_len as _cell_len

    class RippleBorderMixin:
        """Recolour a *bordered* widget's existing CSS border into the rainbow
        ripple — for buttons, inputs, anything with `border: round/...`.

        The widget renders its content and border normally; this only repaints
        the border-ring cells per the travelling-wave rainbow, so labels, typed
        text, and cursors are never disturbed. Use it as the FIRST base class:
        ``class RippleButton(RippleBorderMixin, Button): ...``.

        It activates ONLY when the live theme asks every border to go rainbow
        (``effects.ripple.hue_cycle``) — otherwise render_lines is a pure
        pass-through, so the widget looks exactly as it always did under other
        themes. It also yields while a feedback state class ('flash'/'running')
        is set, so click/just-ran signalling still reads. Honors the same
        reduced-motion / kill switches (a frozen rainbow, no timer).

        NB: only mix into widgets that actually draw a border — on a borderless
        widget the edge cells are content, not frame, and must not be recoloured.
        """
        # anti-lag-d: 0.06 (16.7fps) → 0.1 (10fps), matching RippleFrame.
        # This tick drives the ever-visible input box's border glow the
        # whole session; 10fps is visually identical for a slow glow sweep.
        RIPPLE_TICK = 0.1

        def on_mount(self) -> None:
            _sup = getattr(super(), "on_mount", None)
            if callable(_sup):
                _sup()
            self._rbm_t0 = time.monotonic()
            self._rbm_timer = None
            try:
                self.app.theme_changed_signal.subscribe(self, lambda *_: self._rbm_tick())
            except Exception:  # noqa: BLE001
                pass
            if not ripple_motion_disabled():
                self._rbm_timer = self.set_interval(self.RIPPLE_TICK, self._rbm_tick)

        def _rbm_tick(self) -> None:
            # Guarded refresh. During app teardown (e.g. Ctrl-Q after the cockpit
            # has idled) a still-pending interval can fire against a widget that
            # is already detaching; never let that throw a traceback on the way
            # out. Pure safety - a no-op if we're no longer live.
            try:
                if getattr(self, "is_running", True) and getattr(self, "is_mounted", True):
                    self.refresh()
            except Exception:  # noqa: BLE001
                pass

        def on_unmount(self) -> None:
            _sup = getattr(super(), "on_unmount", None)
            if callable(_sup):
                _sup()
            t = getattr(self, "_rbm_timer", None)
            if t is not None:
                t.stop()
                self._rbm_timer = None

        def _ripple_border_active(self) -> bool:
            # Yield to transient feedback states so a click/run still signals.
            try:
                if self.has_class("flash") or self.has_class("running"):
                    return False
            except Exception:  # noqa: BLE001
                pass
            # Default ON in every theme (matching the main frame) so the
            # buttons + the input glow like the big box. A theme opts its
            # widgets out with effects.ripple.widgets=false (or
            # borders=false). Reduced-motion renders a frozen glow rather
            # than disabling it (handled by ripple_motion_disabled below).
            try:
                getter = getattr(self.app, "active_ripple_effects", None)
                eff = getter() if callable(getter) else {}
            except Exception:  # noqa: BLE001
                eff = {}
            if isinstance(eff, dict) and (eff.get("widgets") is False
                                          or eff.get("borders") is False):
                return False
            return True

        def render_lines(self, crop: "Region") -> "list[Strip]":
            strips = super().render_lines(crop)
            if not self._ripple_border_active():
                return strips
            size = self.outer_size
            w, h = size.width, size.height
            if w < 2 or h < 2:
                return strips
            try:
                _getter = getattr(self.app, "active_ripple_effects", None)
                _eff = _getter() if callable(_getter) else {}
            except Exception:  # noqa: BLE001
                _eff = {}
            _eff = _eff if isinstance(_eff, dict) else {}
            if _eff.get("hue_cycle"):
                params = RIPPLE_AURORA          # rainbow; base colour ignored
                _base_rgb = (167, 139, 250)
            else:
                # Single-colour glow drawn from the theme, exactly like the
                # main frame: RIPPLE_IDLE's slot, tunable per theme.
                params = merge_ripple_params(RIPPLE_IDLE, _eff)
                _base_rgb = resolve_theme_rgb(self.app, params.color_slot,
                                              "primary", "accent",
                                              fallback=(167, 139, 250))
            now = (0.0 if ripple_motion_disabled()
                   else time.monotonic() - getattr(self, "_rbm_t0", time.monotonic()))
            # Fade the resting (trough) border into the widget's OWN concrete
            # background, not a re-resolved theme slot. This guarantees the
            # between-glow border melts into the real surface and can never
            # inherit a terminal/desktop-default colour through this path.
            try:
                _wb = self.styles.background
                if _wb is not None and getattr(_wb, "a", 1) and _wb.a > 0:
                    bg = (_wb.r, _wb.g, _wb.b)
                else:
                    bg = resolve_theme_rgb(self.app, "surface", "panel", "background",
                                           fallback=_FALLBACK_BG)
            except Exception:  # noqa: BLE001
                bg = resolve_theme_rgb(self.app, "surface", "panel", "background",
                                       fallback=_FALLBACK_BG)
            per = perimeter_distance_count(w, h)

            def style_at(x: int, y: int, orig):
                d = perimeter_cell_distance(x, y, w, h)
                if d is None:
                    return None
                r, g, b = ripple_cell_rgb(d, now, per, _base_rgb, bg, params)
                return (orig or Style()) + Style(color=f"rgb({r},{g},{b})")

            def recolor(strip: "Strip", y: int) -> "Strip":
                # Only split a segment when it actually spans a border cell on
                # this row; content segments pass through whole (wide glyphs
                # included). Robust to partial crops.
                out = []
                col = crop.x
                for seg in strip:
                    n = _cell_len(seg.text)
                    if any(perimeter_cell_distance(c, y, w, h) is not None
                           for c in range(col, col + n)):
                        for ch in seg.text:
                            ns = style_at(col, y, seg.style)
                            out.append(Segment(ch, ns if ns is not None else seg.style))
                            col += _cell_len(ch)
                    else:
                        out.append(seg)
                        col += n
                return Strip(list(Segment.simplify(out)), strip.cell_length)

            return [recolor(s, crop.y + i) for i, s in enumerate(strips)]

    __all__ += ["RippleBorderMixin"]

    __all__ += ["RippleFrame", "ripple_frame_strips", "resolve_theme_rgb"]

except ImportError:  # pragma: no cover - Textual not installed
    pass
