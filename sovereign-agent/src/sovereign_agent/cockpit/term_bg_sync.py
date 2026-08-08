"""cockpit/term_bg_sync.py — keep the terminal's own background in lockstep
with Aria's live surface, so sub-pixel cell seams stop revealing the desktop
accent.

WHY THIS EXISTS
---------------
On a fractionally-scaled display the GPU terminal rasterizes character cells on
non-integer pixel boundaries and leaves a ~1px seam between adjacent per-cell
quads. A seam is a window straight *through* the cell layer to the TERMINAL
WINDOW BACKGROUND. Under COSMIC that background follows the desktop accent, so
the seams on Aria's rippling borders glow with the accent and shift whenever it
changes — the "faint accent-coloured lines bleeding into the borders".

Aria cannot paint into a sub-pixel seam: the gap lives *below* Textual's cell
model, in the terminal's own framebuffer-clear colour. But Aria CAN choose the
colour that clear uses. The OSC 11 escape sequence sets the terminal's
default / window background colour. Pin it to Aria's active ``$surface`` and the
seams reveal surface-on-surface — invisible — in any terminal that honours
OSC 11, and it re-matches automatically on every theme change.

This is the complete fix for the *colour* of the seams (it hides them
everywhere — borders, buttons, gaps — not just on the ripple). The companion
``aria-ripple-coalesce`` drop reduces the *number* of seams by merging
same-coloured border runs; the two are independent.

WHAT IT DOES
------------
  • on install  — emit OSC 11 = the active surface.
  • on theme switch — re-emit OSC 11 = the new surface (rides
    ``theme_changed_signal`` — the same signal the ripple uses — with a slow
    poll as a belt-and-suspenders fallback).
  • on process exit — OSC 111 (reset the terminal background to its own
    configured default), via ``atexit`` so it fires *after* Textual has
    restored the normal screen.

SAFETY
------
  • Pure no-op unless stdout is a real TTY (``os.isatty``), mirroring
    ``glyph_metrics``.
  • Kill switch ``SOV_NO_TERM_BG_SYNC=1`` disables the whole module.
  • Every terminal write and the teardown path is wrapped — it never throws
    into the cockpit and never litters the screen (OSC sets terminal *state*,
    not screen cells), so it is safe during Ctrl-Q teardown.
  • Imports cleanly without Textual; the escape-string builders are pure and
    unit-tested. The installer is inert when no app/TTY context is present.

BOUNDARY (unverified from outside the live machine)
---------------------------------------------------
Whether COSMIC Terminal honours OSC 11 / OSC 111, or hard-overrides its
background from the COSMIC system theme. If it honours OSC 11, this is the whole
fix and theme-following is free. If it ignores OSC 11, this module is a silent
no-op (does no harm) and the fallback is to pin cosmic-term to a *fixed* dark
colour scheme in its own settings. Verify by eye on the cockpit.
"""

from __future__ import annotations

import atexit
import os
import re
import sys
from typing import Optional

# ── kill switch ─────────────────────────────────────────────────────────────
BG_SYNC_KILL_SWITCH_ENV = "SOV_NO_TERM_BG_SYNC"

# OSC strings. BEL-terminated form (``ESC ] … BEL``) is the most widely accepted,
# including alacritty-core terminals. OSC 11 sets, OSC 111 resets, the default
# background colour.
_OSC = "\x1b]"
_BEL = "\x07"

__all__ = [
    "BG_SYNC_KILL_SWITCH_ENV",
    "normalize_hex",
    "osc_set_background",
    "osc_reset_background",
    "bg_sync_disabled",
    "resolve_surface_hex",
    "TerminalBackgroundSync",
    "install_terminal_bg_sync",
]

_HEX6_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_HEX3_RE = re.compile(r"^#?([0-9a-fA-F]{3})$")


# ── pure helpers (unit-tested) ───────────────────────────────────────────────
def normalize_hex(value: object) -> Optional[str]:
    """Coerce a colour-ish value to ``'#RRGGBB'`` (upper-case), or ``None``.

    Accepts ``'#abc'``, ``'#aabbcc'``, ``'aabbcc'``, or any object whose
    ``.hex`` attribute or ``str()`` is one of those forms (e.g. a Textual
    ``Color``).
    """
    if value is None:
        return None
    candidate = getattr(value, "hex", None)
    if not isinstance(candidate, str):
        candidate = str(value)
    candidate = candidate.strip()
    m = _HEX6_RE.match(candidate)
    if m:
        return "#" + m.group(1).upper()
    m = _HEX3_RE.match(candidate)
    if m:
        r, g, b = m.group(1)
        return ("#" + r + r + g + g + b + b).upper()
    return None


def osc_set_background(hex_color: str) -> str:
    """OSC 11 'set default background' string for ``#RRGGBB``, or ``''`` if invalid."""
    h = normalize_hex(hex_color)
    if h is None:
        return ""
    return f"{_OSC}11;{h}{_BEL}"


def osc_reset_background() -> str:
    """OSC 111 'reset default background to the terminal's configured default'."""
    return f"{_OSC}111{_BEL}"


def bg_sync_disabled() -> bool:
    """True when the operator has set the kill-switch env var."""
    return bool(os.environ.get(BG_SYNC_KILL_SWITCH_ENV))


def resolve_surface_hex(app: object) -> Optional[str]:
    """The active theme's surface (→ panel → background) as ``'#RRGGBB'``, else ``None``.

    Never raises; returns ``None`` when no theme/colour can be resolved.
    """
    theme = None
    try:
        theme = app.current_theme  # type: ignore[attr-defined]
    except Exception:
        try:
            name = getattr(app, "theme", "") or ""
            theme = app.get_theme(name)  # type: ignore[attr-defined]
        except Exception:
            theme = None
    if theme is None:
        return None
    for slot in ("surface", "panel", "background"):
        h = normalize_hex(getattr(theme, slot, None))
        if h:
            return h
    return None


# ── terminal I/O (guarded, never raises) ─────────────────────────────────────
def _stdout_is_tty() -> bool:
    try:
        return bool(sys.stdout) and os.isatty(sys.stdout.fileno())
    except Exception:
        return False


def _write_raw(seq: str) -> None:
    """Best-effort write of an OSC string straight to the stdout fd.

    OSC 11/111 set terminal *state*, not screen cells, so this composes with
    Textual's renderer without leaving visible litter (same approach as the
    ``glyph_metrics`` DSR probe). Never raises.
    """
    if not seq:
        return
    try:
        os.write(sys.stdout.fileno(), seq.encode("utf-8", "replace"))
    except Exception:
        pass


# ── the sync ──────────────────────────────────────────────────────────────────
class TerminalBackgroundSync:
    """Pins the terminal's window/default background to Aria's live surface.

    Install once from ``App.on_mount`` via :func:`install_terminal_bg_sync`. It
    emits the current surface immediately, re-emits on every theme change, and
    resets the terminal background on process exit. Inert (a pure no-op) when
    the kill switch is set or stdout is not a TTY.
    """

    POLL_SECONDS = 2.0  # fallback re-check; only writes when the surface changes

    def __init__(self, app: object) -> None:
        self._app = app
        self._last: Optional[str] = None  # last surface we emitted
        self._restored = False
        self._timer = None
        self._active = False

    # -- lifecycle --
    def install(self) -> "TerminalBackgroundSync":
        if bg_sync_disabled() or not _stdout_is_tty():
            return self  # inert
        self._active = True
        # Restore the terminal's own default bg when the process ends. atexit
        # fires AFTER Textual restores the normal screen — the clean moment.
        try:
            atexit.register(self._restore)
        except Exception:
            pass
        # Emit the active surface now.
        self._emit()
        # Instant updates on theme switch (the signal the ripple also rides).
        try:
            self._app.theme_changed_signal.subscribe(  # type: ignore[attr-defined]
                self._app, lambda *_: self._emit()
            )
        except Exception:
            pass
        # Belt-and-suspenders: a slow poll catches any change the signal misses.
        try:
            self._timer = self._app.set_interval(self.POLL_SECONDS, self._emit)  # type: ignore[attr-defined]
        except Exception:
            self._timer = None
        return self

    def _emit(self) -> None:
        if not self._active:
            return
        try:
            surface = resolve_surface_hex(self._app)
        except Exception:
            surface = None
        if not surface or surface == self._last:
            return
        _write_raw(osc_set_background(surface))
        self._last = surface

    def _restore(self) -> None:
        if self._restored or not self._active:
            return
        self._restored = True
        _write_raw(osc_reset_background())

    def stop(self) -> None:
        """Stop the poll timer and restore the terminal background now."""
        timer = self._timer
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            self._timer = None
        self._restore()


def install_terminal_bg_sync(app: object) -> Optional[TerminalBackgroundSync]:
    """Create and install a :class:`TerminalBackgroundSync` for ``app``.

    Returns the (possibly inert) instance, or ``None`` on unexpected failure.
    Safe to call once from ``App.on_mount``; never raises into the cockpit.
    """
    try:
        return TerminalBackgroundSync(app).install()
    except Exception:
        return None
