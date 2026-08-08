"""Glyph width accounting — measure what THIS terminal actually does.

The whole width problem comes down to one disagreement: rich/Textual compute a
glyph's width from a Unicode table (``cell_len``), but the terminal+font draw it
at whatever width they like. For East-Asian-*Ambiguous* glyphs (hearts, stars,
circles, ◊) and many emoji, those two numbers differ — and every cell after the
glyph on that line, including borders, slides by the difference. No amount of
padding fixes it, because rich re-measures padded text with the same wrong table
and undoes the compensation. The *only* complete fix is to make ``cell_len``
return the terminal's REAL widths, which means measuring them.

This module measures and then offers two tiers of use:

  • Tier 1 — MEASURE → CLASSIFY (safe, recommended).
        Probe the terminal, learn which glyphs it actually draws at >1 cell,
        and feed that into the existing safe-handling (badge them / keep them
        out of counted layouts). No rendering is patched; nothing can break.
        `probe_terminal_widths()` + `overwide_glyphs()`.

  • Tier 2 — MEASURE → COMPENSATE (experimental, opt-in, OFF by default).
        Actually teach rich/Textual the measured widths so even wide glyphs lay
        out correctly. This patches `cell_len` in rich AND in Textual's modules
        that bound it directly — powerful, but coupled to library internals and
        unvalidated on terminals we haven't seen, so it is gated behind an env
        var and is fully reversible. `install_width_overrides()`.

The measurement itself uses DSR (Device Status Report): write a glyph, ask the
terminal "where is the cursor now?" (`ESC[6n`), and read back `ESC[row;colR`.
The column delta IS the real rendered width, for this terminal and font, right
now. It requires a real TTY and is done with the app's screen control
suspended; on anything else it degrades cleanly to "measured nothing", and the
cockpit keeps its current (safe) behavior.

Kill switches:
  • SOV_NO_GLYPH_METRICS=1     — never probe (probe returns an empty table).
  • SOV_GLYPH_WIDTH_OVERRIDE=1 — allow Tier 2 overrides to be installed.
"""
from __future__ import annotations

import contextlib
import os
import re
import sys
from dataclasses import dataclass, field

__all__ = [
    "WidthTable",
    "parse_dsr_column",
    "metrics_enabled",
    "width_override_allowed",
    "probe_terminal_widths",
    "overwide_glyphs",
    "normalize_frames",
    "install_width_overrides",
    "uninstall_width_overrides",
]

METRICS_KILL_ENV = "SOV_NO_GLYPH_METRICS"
OVERRIDE_ENABLE_ENV = "SOV_GLYPH_WIDTH_OVERRIDE"

# DSR reply looks like ESC [ <row> ; <col> R  (CSI Ps n response).
_DSR_RE = re.compile(rb"\x1b\[(\d+);(\d+)R")


def metrics_enabled() -> bool:
    """False if probing is disabled by kill switch."""
    return os.environ.get(METRICS_KILL_ENV, "") == ""


def width_override_allowed() -> bool:
    """Tier 2 overrides may only be installed when explicitly enabled."""
    return os.environ.get(OVERRIDE_ENABLE_ENV, "") not in ("", "0", "false")


# ─────────────────────────────────────────────────────────────────────────────
#  WidthTable — measured glyph → real cell width on THIS terminal
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class WidthTable:
    """A measured map of glyph → cell width for the current terminal.

    Only contains glyphs we actually measured; absence means "unknown, fall
    back to rich". Serialisable so a probe result can be cached between runs.
    """

    widths: dict[str, int] = field(default_factory=dict)
    term: str = ""

    def get(self, glyph: str) -> int | None:
        return self.widths.get(glyph)

    def set(self, glyph: str, width: int) -> None:
        if width >= 0:
            self.widths[glyph] = width

    def __contains__(self, glyph: str) -> bool:
        return glyph in self.widths

    def __len__(self) -> int:
        return len(self.widths)

    def __bool__(self) -> bool:
        return bool(self.widths)

    def merge(self, other: WidthTable) -> WidthTable:
        merged = dict(self.widths)
        merged.update(other.widths)
        return WidthTable(widths=merged, term=other.term or self.term)

    def to_dict(self) -> dict:
        return {"term": self.term, "widths": dict(self.widths)}

    @classmethod
    def from_dict(cls, data: dict) -> WidthTable:
        return cls(
            widths={str(k): int(v) for k, v in data.get("widths", {}).items()},
            term=str(data.get("term", "")),
        )


def parse_dsr_column(data: bytes) -> int | None:
    """Extract the cursor COLUMN from a DSR reply, or None if absent.

    Pulled out as a pure function so the protocol parsing is testable without a
    terminal. ``data`` may contain other bytes; we take the last match.
    """
    matches = list(_DSR_RE.finditer(data))
    if not matches:
        return None
    return int(matches[-1].group(2))


# ─────────────────────────────────────────────────────────────────────────────
#  The probe — DSR cursor-position measurement (real TTY only)
# ─────────────────────────────────────────────────────────────────────────────
def _read_dsr_reply(fd: int, timeout: float) -> bytes:
    """Read a DSR reply from fd with a timeout. Returns raw bytes (maybe empty)."""
    import select

    buf = bytearray()
    deadline_budget = timeout
    while deadline_budget > 0:
        r, _, _ = select.select([fd], [], [], deadline_budget)
        if not r:
            break
        chunk = os.read(fd, 32)
        if not chunk:
            break
        buf.extend(chunk)
        if b"R" in chunk:  # terminator of the CSI ... R reply
            break
        deadline_budget *= 0.5
    return bytes(buf)


def probe_terminal_widths(
    glyphs: list[str],
    *,
    stream=None,
    timeout: float = 0.15,
) -> WidthTable:
    """Measure the real rendered width of each glyph on the current terminal.

    Writes each glyph at a known column and asks the terminal for the cursor
    position; the column delta is the true width. Cleans up the line after each
    measurement. Returns a WidthTable of everything measured.

    Safe by construction: if metrics are disabled, stdin/stdout are not a TTY,
    termios is unavailable, or the terminal never answers, this returns an empty
    table and the caller simply keeps rich's default widths. It must be called
    with any full-screen app's control SUSPENDED (e.g. inside Textual's
    ``App.suspend()``), since it writes raw escape sequences.
    """
    table = WidthTable(term=os.environ.get("TERM", ""))
    if not metrics_enabled() or not glyphs:
        return table

    out = stream or sys.stdout
    try:
        in_fd = sys.stdin.fileno()
        out_fd = out.fileno()
    except Exception:  # noqa: BLE001 - not real streams
        return table
    if not (os.isatty(in_fd) and os.isatty(out_fd)):
        return table

    try:
        import termios
        import tty
    except Exception:  # noqa: BLE001 - non-Unix
        return table

    def _w(s: str) -> None:
        os.write(out_fd, s.encode("utf-8", "replace"))

    old = None
    try:
        old = termios.tcgetattr(in_fd)
        tty.setraw(in_fd)
        # Confirm the terminal answers DSR at all before trusting anything.
        _w("\x1b[6n")
        if parse_dsr_column(_read_dsr_reply(in_fd, timeout)) is None:
            return table  # no DSR support → keep defaults
        for g in glyphs:
            if not g:
                continue
            _w("\r")              # cursor to column 1
            _w("\x1b[6n")
            start = parse_dsr_column(_read_dsr_reply(in_fd, timeout))
            _w(g)                  # draw the glyph
            _w("\x1b[6n")
            end = parse_dsr_column(_read_dsr_reply(in_fd, timeout))
            _w("\r\x1b[2K")       # wipe the line (no visible litter)
            if start is not None and end is not None:
                width = end - start
                if 0 <= width <= 4:   # sane bound; reject garbage replies
                    table.set(g, width)
    except Exception:  # noqa: BLE001, S110 — partial table is fine; finally restores TTY
        pass
    finally:
        if old is not None:
            with contextlib.suppress(Exception):
                termios.tcsetattr(in_fd, termios.TCSADRAIN, old)
        with contextlib.suppress(Exception):
            _w("\r\x1b[2K")
    return table


# ─────────────────────────────────────────────────────────────────────────────
#  Tier 1 — measure → classify (safe)
# ─────────────────────────────────────────────────────────────────────────────
def overwide_glyphs(table: WidthTable, threshold: int = 2) -> set[str]:
    """Glyphs this terminal draws at >= threshold cells.

    Feed these into the existing not-layout-safe handling (badge them, keep them
    out of counted layouts). This is the safe use of a probe: it informs
    curation; it patches no rendering.
    """
    return {g for g, w in table.widths.items() if w >= threshold}


def normalize_frames(
    frames: tuple[str, ...] | list[str],
    table: WidthTable,
    *,
    fallback_width: int = 1,
) -> tuple[tuple[str, ...], int]:
    """Pad each animation frame with trailing spaces to a constant TRUE width.

    The target is the widest measured frame (or ``fallback_width`` if none are
    known). This removes per-frame JITTER — every frame occupies the same number
    of real cells. NOTE: this only fully prevents border movement when the
    layout also reserves that true width, i.e. when Tier 2 overrides are
    installed; otherwise rich would re-clip the padding by its own (wrong) model.
    """
    measured = [table.get(f) for f in frames]
    known = [w for w in measured if w is not None]
    target = max(known) if known else fallback_width
    padded: list[str] = []
    for f, w in zip(frames, measured, strict=False):
        w = w if w is not None else fallback_width
        pad = max(0, target - w)
        padded.append(f + " " * pad)
    return tuple(padded), target


# ─────────────────────────────────────────────────────────────────────────────
#  Tier 2 — measure → compensate (EXPERIMENTAL, opt-in, default OFF)
# ─────────────────────────────────────────────────────────────────────────────
# Teaching rich/Textual the measured widths means overriding cell_len. Textual
# binds it via ``from rich.cells import cell_len`` in several modules, so each
# binding has to be repointed; rich's cached_cell_len is LRU-cached, so the
# cache is cleared. All originals are saved for a clean uninstall.
_OVERRIDE_STATE: dict[str, object] = {}


def _textual_cell_len_sites() -> list:
    """Modules holding a direct `cell_len` binding we must repoint. Best-effort:
    only those importable in this environment are returned."""
    import importlib

    sites = []
    for modname in (
        "textual._cells",
        "textual.strip",
        "textual.render",
        "textual.expand_tabs",
        "textual.renderables.text_opacity",
    ):
        try:
            mod = importlib.import_module(modname)
        except Exception:  # noqa: BLE001, S112
            continue
        if hasattr(mod, "cell_len"):
            sites.append(mod)
    return sites


def install_width_overrides(table: WidthTable, *, force: bool = False) -> bool:
    """EXPERIMENTAL: make rich/Textual measure the given glyphs at their true
    widths. Returns True if installed.

    Refuses unless ``SOV_GLYPH_WIDTH_OVERRIDE`` is set (or ``force=True``),
    because it patches library internals and is unvalidated on terminals we have
    not measured. Fully reversible via ``uninstall_width_overrides()``.
    """
    if not table:
        return False
    if not force and not width_override_allowed():
        return False
    if _OVERRIDE_STATE:
        return True  # already installed

    import rich.cells as rc

    widths = dict(table.widths)
    orig_cell_len = rc.cell_len
    orig_cached = rc.cached_cell_len

    def patched_cell_len(text: str, unicode_version: str = "auto") -> int:
        w = widths.get(text)
        if w is not None:
            return w
        # also handle the common single-glyph case embedded in a 1-char string
        if len(text) == 1:
            return orig_cell_len(text, unicode_version)
        return orig_cell_len(text, unicode_version)

    def patched_cached(text: str, unicode_version: str = "auto") -> int:
        w = widths.get(text)
        return w if w is not None else orig_cached(text, unicode_version)

    # Save originals.
    _OVERRIDE_STATE["rich_cell_len"] = orig_cell_len
    _OVERRIDE_STATE["rich_cached"] = orig_cached
    _OVERRIDE_STATE["sites"] = []

    # Patch rich.
    rc.cell_len = patched_cell_len  # type: ignore[assignment]
    rc.cached_cell_len = patched_cached  # type: ignore[assignment]
    with contextlib.suppress(Exception):
        rc.cached_cell_len.cache_clear()  # type: ignore[attr-defined]

    # Repoint Textual's direct bindings.
    for mod in _textual_cell_len_sites():
        _OVERRIDE_STATE["sites"].append((mod, mod.cell_len))  # type: ignore[union-attr]
        # _cells binds cached_cell_len as cell_len; everyone else binds cell_len.
        mod.cell_len = (  # type: ignore[attr-defined]
            patched_cached if mod.__name__ == "textual._cells" else patched_cell_len
        )
    return True


def uninstall_width_overrides() -> bool:
    """Undo install_width_overrides(). Returns True if something was removed."""
    if not _OVERRIDE_STATE:
        return False
    import rich.cells as rc

    rc.cell_len = _OVERRIDE_STATE.get("rich_cell_len", rc.cell_len)  # type: ignore
    rc.cached_cell_len = _OVERRIDE_STATE.get("rich_cached", rc.cached_cell_len)  # type: ignore
    with contextlib.suppress(Exception):
        rc.cached_cell_len.cache_clear()  # type: ignore[attr-defined]
    for mod, original in _OVERRIDE_STATE.get("sites", []):  # type: ignore
        with contextlib.suppress(Exception):
            mod.cell_len = original
    _OVERRIDE_STATE.clear()
    return True
