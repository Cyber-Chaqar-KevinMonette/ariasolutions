"""
animated_glyph.py — AnimatedGlyph: a frame-cycling "living glyph" widget.

Where breathing_glyph.py modulates the *brightness* of a single glyph along a
sine wave, AnimatedGlyph cycles through a *sequence of frames* (a spinner, a
pulsing meter, the moon's phases, a dancing emoji). It is driven by the
AnimationSpec catalog in cosmic_fitness.py.

Safety
    • Layout-safe animations (every frame one cell — braille, blessed blocks,
      circles, single-cell stars) can run anywhere, including the main UI.
    • Sandbox-only animations (any frame emoji/wide) must live inside a
      GlyphStage (glyph_stage.py), whose fixed footprint and clipped overflow
      keep a 2-cell frame from shifting the surrounding layout.

    To make accidental misuse loud rather than silent, AnimatedGlyph refuses a
    sandbox-only animation outside a stage *unless* you pass
    ``assume_width_safe=True`` (the same informed-caller escape hatch as
    breathing_glyph). It cannot tell whether its parent is a GlyphStage, so the
    flag is how the caller asserts "I've boxed this."

Reduced motion / kill switches
    Honors SOV_NO_GLYPH_ANIMATION=1 and SOV_REDUCED_MOTION=1: either one freezes
    the widget on a single representative frame (no timer), for low-power
    terminals, screen recordings, or motion-sensitivity.

Imports cleanly without Textual (the widget is only defined when Textual is
importable), mirroring breathing_glyph.py.
"""
from __future__ import annotations

import os

ANIM_KILL_SWITCH_ENV = "SOV_NO_GLYPH_ANIMATION"
REDUCED_MOTION_ENV = "SOV_REDUCED_MOTION"

__all__ = ["ANIM_KILL_SWITCH_ENV", "REDUCED_MOTION_ENV"]


def animation_disabled() -> bool:
    """True if either the animation kill switch or reduced-motion is set."""
    return bool(os.environ.get(ANIM_KILL_SWITCH_ENV) or
                os.environ.get(REDUCED_MOTION_ENV))


try:  # pragma: no cover - exercised only when Textual is present
    from textual.widgets import Static

    from .cosmic_fitness import AnimationSpec, classify_glyph

    class AnimatedGlyph(Static):
        """A glyph that cycles through frames on a timer.

        Construct from an AnimationSpec, or pass frames + fps directly.

        Parameters
        ----------
        spec:
            An AnimationSpec from the catalog. If given, supplies frames/fps.
        frames, fps:
            Used when no spec is given (ad-hoc animation).
        cells:
            Fixed cell width for the widget. Defaults to 1 for a layout-safe
            animation and 2 for a sandbox-only one, so the widget's own
            footprint is stable regardless of how a terminal sizes the frame.
        assume_width_safe:
            Required (True) to run a sandbox-only animation; asserts the caller
            has placed it inside a GlyphStage. Layout-safe animations ignore it.
        """

        def __init__(
            self,
            spec: AnimationSpec | None = None,
            *,
            frames: tuple[str, ...] | None = None,
            fps: float = 8.0,
            cells: int | None = None,
            assume_width_safe: bool = False,
            **kwargs,
        ) -> None:
            if spec is not None:
                self._frames = tuple(spec.frames)
                self._interval = spec.interval
                self._spec = spec
                layout_safe = spec.is_layout_safe
            else:
                if not frames:
                    raise ValueError("AnimatedGlyph needs a spec or non-empty frames")
                self._frames = tuple(frames)
                self._interval = 1.0 / fps if fps > 0 else 0.125
                self._spec = None
                layout_safe = all(
                    classify_glyph(f)[0] in ("safe", "convention")
                    for f in self._frames
                )

            if not layout_safe and not assume_width_safe:
                raise ValueError(
                    "this animation has wide/emoji frames; place it inside a "
                    "GlyphStage and pass assume_width_safe=True"
                )

            self._cells = cells if cells is not None else (1 if layout_safe else 2)
            self._idx = 0
            self._timer = None
            super().__init__(self._frames[0], **kwargs)

        @property
        def is_animating(self) -> bool:
            return self._timer is not None

        @property
        def current_frame(self) -> str:
            """The frame currently displayed."""
            return self._frames[self._idx]

        def on_mount(self) -> None:
            self.styles.width = self._cells
            # clip in-cell so a frame the terminal draws wider than its
            # reserved width is cut here rather than nudging a neighbour.
            self.styles.overflow_x = "hidden"
            if animation_disabled():
                # Reduced motion: hold a single representative frame, no timer.
                self.update(self._frames[len(self._frames) // 2])
                return
            self._timer = self.set_interval(self._interval, self._advance)

        def on_unmount(self) -> None:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None

        def _advance(self) -> None:
            self._idx = (self._idx + 1) % len(self._frames)
            self.update(self._frames[self._idx])

    __all__ += ["AnimatedGlyph"]

    import time as _time

    from .cosmic_fitness import AnimatedEffectSpec, effect_color_at

    class AnimatedEffect(Static):
        """An animated special effect: a frame sequence painted with a live
        brightness ('glow') or colour ('hue') modulation.

        This is the union of AnimatedGlyph (frames) and the breathing-glyph
        idea (modulation) — e.g. the beating heart (♥↔♡ + cardiac glow) or the
        Aurora circle (one glyph, drifting hue). Frame index and colour are
        both derived from elapsed time, so a single smooth timer drives both.

        Same safety contract as AnimatedGlyph: sandbox-only specs (wide/emoji
        frames) require assume_width_safe=True (i.e. placed in a GlyphStage).
        Honors SOV_NO_GLYPH_ANIMATION / SOV_REDUCED_MOTION (holds one frame,
        base colour, no timer).
        """

        # ~17fps render tick — smooth enough for a glow, light enough for many.
        _TICK = 0.06

        def __init__(
            self,
            spec: AnimatedEffectSpec,
            *,
            cells: int | None = None,
            assume_width_safe: bool = False,
            **kwargs,
        ) -> None:
            if not spec.is_layout_safe and not assume_width_safe:
                raise ValueError(
                    "this animated effect has wide/emoji frames; place it in a "
                    "GlyphStage and pass assume_width_safe=True"
                )
            self._spec = spec
            self._cells = cells if cells is not None else (
                1 if spec.is_layout_safe else 2
            )
            self._t0 = _time.monotonic()
            self._timer = None
            super().__init__(spec.frames[0], **kwargs)

        @property
        def is_animating(self) -> bool:
            return self._timer is not None

        def _frame_at(self, elapsed: float) -> str:
            n = len(self._spec.frames)
            idx = int(elapsed * self._spec.frame_fps) % n if n else 0
            return self._spec.frames[idx]

        def on_mount(self) -> None:
            self.styles.width = self._cells
            # clip in-cell so a frame the terminal draws wider than its
            # reserved width is cut here rather than nudging a neighbour.
            self.styles.overflow_x = "hidden"
            if animation_disabled():
                mid = self._spec.frames[len(self._spec.frames) // 2]
                self.update(f"[{self._spec.base_hex}]{mid}[/]")
                return
            self._timer = self.set_interval(self._TICK, self._tick)

        def on_unmount(self) -> None:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None

        def _tick(self) -> None:
            elapsed = _time.monotonic() - self._t0
            frame = self._frame_at(elapsed)
            color = effect_color_at(self._spec, elapsed)
            self.update(f"[{color}]{frame}[/]")

    __all__ += ["AnimatedEffect"]

except ImportError:  # pragma: no cover - Textual not installed
    pass
