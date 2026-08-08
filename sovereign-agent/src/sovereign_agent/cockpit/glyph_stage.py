"""
glyph_stage.py — the GlyphStage: a bounded viewport that geometrically
isolates unstable glyphs from the rest of the TUI.

THE PROBLEM (Kevin's insight, v0.2.42)
    Some Unicode glyphs render one cell wide in one terminal and two cells
    wide in another — emoji, emoji-variation marks (❤ ☀ ▶), CJK, ZWJ
    sequences. When such a glyph lands in the main UI layer, the terminal's
    own cursor math desyncs and *everything downstream shifts*: borders break,
    columns misalign, the whole frame glitches. The width law says: keep them
    out of the layout.

THE UNLOCK
    But you can still SHOW them — safely — if you put them in a container whose
    OUTER footprint is fixed by declaration rather than measured from its
    contents. That is a GlyphStage:

        • a fixed, declared width/height (in cells), so the box's geometry is
          known up front and never grows to fit what's inside it;
        • clipped overflow, so a glyph that renders wider than expected is
          cut off at the boundary instead of pushing its neighbours;
        • a visible border, so it reads as its own little viewport.

    The result: a 2-cell emoji (or an animation, or a special effect) inside a
    GlyphStage cannot move a single cell of the UI outside it. Expressive
    visuals, no instability tax.

HONEST LIMITS (calibrated, not oversold)
    This is a *bounded viewport*, not a real nested pseudo-terminal. It fully
    isolates the OUTER layout: siblings and the surrounding frame are pinned by
    the stage's declared size, so they cannot be shifted by anything inside.
    What it does NOT promise is pixel-perfect rendering of unstable glyphs
    *within* the box on every terminal — a 2-cell emoji may still clip or leave
    a gap inside the stage on a terminal that disagrees about its width. That's
    the right trade: the glitch is confined to a small, expected, bordered
    region instead of corrupting the whole interface. A true sub-terminal
    (a real PTY/grid like a tmux pane) would render those glyphs perfectly but
    costs far more complexity and a heavier dependency — boring reliability
    wins here. The door to that heavier approach stays open (see TRAJECTORY).

This module imports cleanly without Textual installed (the widget classes are
only defined when Textual is importable), mirroring breathing_glyph.py.
"""
from __future__ import annotations

import contextlib
import os

# Kill switch: when set, GlyphStage still bounds geometry but drops the border
# chrome (handy for snapshot tests / minimal renders).
PLAIN_STAGE_ENV = "SOV_PLAIN_GLYPH_STAGE"

# Sensible default inner width (in cells) for a stage when the caller doesn't
# pin one. Wide enough for a short row of glyphs; narrow enough to stay tidy.
DEFAULT_STAGE_CELLS = 24

__all__ = ["PLAIN_STAGE_ENV", "DEFAULT_STAGE_CELLS"]


try:  # pragma: no cover - exercised only when Textual is present
    from textual.containers import Container, HorizontalScroll

    class GlyphStage(Container):
        """A bounded, overflow-clipped viewport for layout-unstable glyphs.

        Place wide/emoji/composite glyphs, animations, or special effects in
        here and they cannot shift the surrounding UI: the stage's outer size
        is fixed by ``cells`` / ``rows`` (declared, not content-derived), and
        overflow is clipped.

        Parameters
        ----------
        cells:
            Inner width budget in terminal cells. The outer width is pinned to
            this (plus border), so the footprint never grows with content.
            Defaults to DEFAULT_STAGE_CELLS.
        rows:
            Optional fixed inner height in rows. If omitted, height is auto
            (bounded by the parent) — width isolation is the important axis.
        scroll:
            If True, overflow scrolls instead of clipping (a peek-the-rest
            affordance). Default False (clip) for the strongest isolation.
        title:
            Optional caption rendered as the border title.
        """

        DEFAULT_CSS = """
        GlyphStage {
            width: auto;
            height: auto;
            max-width: 100%;
            overflow-x: hidden;
            overflow-y: hidden;
            border: round $secondary;
            background: $panel;
            padding: 0 1;
        }
        GlyphStage.-plain {
            border: none;
            background: transparent;
            padding: 0;
        }
        GlyphStage.-scroll {
            overflow-x: auto;
        }
        GlyphStage.-ripple {
            /* Ripple mode: drop the CSS border and reserve a one-cell ring with
               padding instead; the rippling frame is custom-painted into that
               ring by render_lines (see ripple_border.py). Width-pin and
               clipped overflow are unchanged, so the stage stays bounded. */
            border: none;
            padding: 1;
        }
        """

        def __init__(
            self,
            *children,
            cells: int | None = None,
            rows: int | None = None,
            scroll: bool = False,
            title: str | None = None,
            ripple: bool = False,
            ripple_aurora: bool = False,
            ripple_base_hex: str = "#7DD3FC",
            ripple_bg_hex: str = "#171226",
            **kwargs,
        ) -> None:
            super().__init__(*children, **kwargs)
            self._cells = DEFAULT_STAGE_CELLS if cells is None else max(2, int(cells))
            self._rows = rows
            self._scroll = scroll
            self._title = title
            # Ripple mode (opt-in): a glow travels around the border. The frame
            # is custom-painted in render_lines; colours resolve from the live
            # theme at mount (secondary → glow, panel → trough).
            #   ripple_aurora=True → the rainbow variant: a full spectrum wraps
            #   the border and rotates over time while the glow still ripples
            #   (the aurora glyph's hue-cycle, made into a frame).
            self._ripple = ripple or ripple_aurora
            self._ripple_aurora = ripple_aurora
            self._ripple_base_hex = ripple_base_hex
            self._ripple_bg_hex = ripple_bg_hex
            self._ripple_t0 = 0.0
            self._ripple_timer = None
            self._ripple_base_rgb = None
            self._ripple_bg_rgb = None

        def on_mount(self) -> None:
            # Pin the outer geometry. This is the whole point: the box's width
            # is declared, so nothing inside can make the box (or its siblings)
            # grow. We add 2 to cover the border columns under border-box.
            self.styles.width = self._cells + 2
            if self._rows is not None:
                self.styles.height = self._rows + 2
            if self._scroll:
                self.add_class("-scroll")
            if self._title:
                # border_title exists on modern Textual; guard older versions.
                with contextlib.suppress(Exception):
                    self.border_title = self._title
            if os.environ.get(PLAIN_STAGE_ENV):
                self.add_class("-plain")
            # Ripple mode wins over -plain only when not also plain; -plain is a
            # snapshot/minimal mode, so respect it and skip the ripple chrome.
            if self._ripple and not self.has_class("-plain"):
                self._start_ripple()

        # ── ripple mode ─────────────────────────────────────────────────
        def _start_ripple(self) -> None:
            import time as _time

            from .ripple_border import ripple_motion_disabled

            self.add_class("-ripple")
            self._ripple_t0 = _time.monotonic()
            # Resolve glow + trough from the live theme, with fallbacks. (Also
            # re-resolved every frame in render_lines so the stage border tracks
            # theme switches and live hue-cycling themes.)
            self._resolve_ripple_colors()
            # Repaint immediately on a theme switch (covers the static case).
            try:
                self.app.theme_changed_signal.subscribe(self, lambda *_: self.refresh())
            except Exception:  # noqa: BLE001
                pass
            if ripple_motion_disabled():
                self.refresh()  # static frame, no timer
                return
            self._ripple_timer = self.set_interval(0.06, self.refresh)

        def _resolve_ripple_colors(self) -> None:
            from .ripple_border import RIPPLE_STAGE, hex_to_rgb, resolve_theme_rgb
            try:
                self._ripple_base_rgb = resolve_theme_rgb(
                    self.app, RIPPLE_STAGE.color_slot, "secondary", "accent",
                    fallback=self._ripple_base_hex,
                )
                self._ripple_bg_rgb = resolve_theme_rgb(
                    self.app, "panel", "surface", "background",
                    fallback=self._ripple_bg_hex,
                )
            except Exception:  # noqa: BLE001
                self._ripple_base_rgb = hex_to_rgb(self._ripple_base_hex)
                self._ripple_bg_rgb = hex_to_rgb(self._ripple_bg_hex)

        def on_unmount(self) -> None:
            if self._ripple_timer is not None:
                self._ripple_timer.stop()
                self._ripple_timer = None

        def render_lines(self, crop):  # type: ignore[override]
            # Static border: defer to Textual's normal styles-cache rendering.
            if not getattr(self, "_ripple", False) or not self.has_class("-ripple"):
                return super().render_lines(crop)
            import time as _time

            from .ripple_border import (
                RIPPLE_AURORA,
                RIPPLE_STAGE,
                hex_to_rgb,
                ripple_frame_strips,
                ripple_motion_disabled,
            )

            # Re-resolve every frame so the stage border tracks theme switches
            # and live hue-cycling themes (cheap; same rationale as RippleFrame).
            self._resolve_ripple_colors()
            base = self._ripple_base_rgb or hex_to_rgb(self._ripple_base_hex)
            bg = self._ripple_bg_rgb or hex_to_rgb(self._ripple_bg_hex)
            # Aurora (rainbow) ripple if this stage opted in, OR the active theme
            # asks every border to go rainbow (effects.ripple.hue_cycle).
            want_aurora = self._ripple_aurora
            if not want_aurora:
                try:
                    getter = getattr(self.app, "active_ripple_effects", None)
                    if callable(getter):
                        want_aurora = bool(getter().get("hue_cycle"))
                except Exception:  # noqa: BLE001
                    want_aurora = False
            params = RIPPLE_AURORA if want_aurora else RIPPLE_STAGE
            now = 0.0 if ripple_motion_disabled() else (_time.monotonic() - self._ripple_t0)
            size = self.outer_size
            return ripple_frame_strips(
                size.width, size.height, now, base, bg, crop, params,
                title=self._title,
            )

        @property
        def inner_cells(self) -> int:
            """The declared inner width budget, in cells."""
            return self._cells

    class GlyphStageStrip(HorizontalScroll):
        """A one-row GlyphStage variant: a horizontally-scrollable strip with a
        pinned height, for a row of tappable wide/emoji glyphs (e.g. the inline
        picker). Height is fixed so the row can never grow vertically; width
        fills the available space and scrolls horizontally.
        """

        DEFAULT_CSS = """
        GlyphStageStrip {
            height: 3;
            width: 1fr;
            overflow-x: auto;
            overflow-y: hidden;
            background: $panel;
            border: round $secondary;
        }
        """

    __all__ += ["GlyphStage", "GlyphStageStrip"]

except ImportError:  # pragma: no cover - Textual not installed
    pass
