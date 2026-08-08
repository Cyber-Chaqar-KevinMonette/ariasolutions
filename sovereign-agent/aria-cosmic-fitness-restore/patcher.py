"""patcher.py — the P0 fix, as a pure, testable transformation.

Restores CosmicFitnessScreen + WorkflowsScreen (and their supporting cast: GlyphButton,
the guarded `_cf` import, 5 slash-command methods, the /cosmic + /workflows dispatch) into
cockpit/app.py. Commit 8fc7267 rewrote app.py and silently dropped these while
cockpit/__init__.py still imports them — breaking `sov chat` with an ImportError.

Deliberately NOT restored: the separate inline Ctrl-G glyph-picker toggle strip in
compose() (a distinct, larger UI feature living in the main layout, not the modal) and
its palette button. That's tracked as a fast-follow, not part of this crash fix — see
README.md. Three tests in the pre-existing tests/test_cosmic_fitness.py suite
(test_cockpit_still_renders_with_cosmic_wired, test_inline_picker_toggles_and_inserts,
test_cosmic_slash_commands) exercise that deferred surface and stay red until that
follow-up lands; the other 68 tests in that suite pass against this patch.

Pure string transformation — no file I/O of its own, so it's directly unit-testable
against any app.py text without touching the filesystem.
"""
from __future__ import annotations

from pathlib import Path

MARK_GRID = "cosmic-fitness-restore-grid-import-d"
MARK_IMPORT = "cosmic-fitness-restore-import-d"
MARK_CLASSES = "cosmic-fitness-restore-classes-d"
MARK_METHODS = "cosmic-fitness-restore-methods-d"
MARK_DISPATCH = "cosmic-fitness-restore-dispatch-d"

ALL_MARKERS = (MARK_GRID, MARK_IMPORT, MARK_CLASSES, MARK_METHODS, MARK_DISPATCH)


class PatchError(RuntimeError):
    """An expected anchor was missing — app.py drifted further since this was written."""


def _frag(frag_dir: Path, name: str) -> str:
    return (frag_dir / name).read_text(encoding="utf-8").rstrip("\n")


def patch(app_text: str, frag_dir: Path) -> tuple[str, list[str]]:
    """Apply all 5 idempotent patches. Returns (new_text, list_of_changes_made)."""
    t = app_text
    changed: list[str] = []

    if MARK_GRID in t:
        pass
    else:
        anchor = "from textual.containers import Horizontal, Vertical, VerticalScroll"
        if anchor not in t:
            raise PatchError(f"grid-import anchor not found: {anchor!r}")
        replacement = (
            f"from textual.containers import (  # {MARK_GRID}\n"
            "    Grid, Horizontal, Vertical, VerticalScroll,\n"
            ")"
        )
        t = t.replace(anchor, replacement, 1)
        changed.append("grid-import")

    if MARK_IMPORT in t:
        pass
    else:
        anchor = "logger = logging.getLogger(__name__)"
        if anchor not in t:
            raise PatchError(f"import anchor not found: {anchor!r}")
        add = (
            "# v0.2.41 \"Cosmic Fitness\" — the visual-systems gym. Import-safe (no Textual\n"
            "# at import time, no heavy deps). Guarded so a failure here can never block\n"
            "# the cockpit; the button + picker simply won't wire up if it's unavailable.\n"
            "try:\n"
            "    from . import cosmic_fitness as _cf\n"
            "except Exception:  # pragma: no cover — cosmic fitness is strictly optional\n"
            f"    _cf = None  # {MARK_IMPORT}\n\n"
        )
        t = t.replace(anchor, add + anchor, 1)
        changed.append("import")

    if MARK_CLASSES in t:
        pass
    else:
        anchor = "@dataclass(frozen=True)\nclass PaletteCommand:"
        if t.count(anchor) != 1:
            raise PatchError(f"classes anchor not found exactly once (found {t.count(anchor)})")
        block = _frag(frag_dir, "classes_block.py")
        t = t.replace(anchor, block + f"\n# {MARK_CLASSES}\n\n\n" + anchor, 1)
        changed.append("classes")

    if MARK_METHODS in t:
        pass
    else:
        anchor = "    def action_paste_clipboard(self) -> None:"
        if t.count(anchor) != 1:
            raise PatchError(f"methods anchor not found exactly once (found {t.count(anchor)})")
        block = _frag(frag_dir, "methods_block.py")
        t = t.replace(anchor, block + f"\n    # {MARK_METHODS}\n\n" + anchor, 1)
        changed.append("methods")

    if MARK_DISPATCH in t:
        pass
    else:
        anchor = '        else:\n            self._write_meta(f"unknown command: /{verb}")'
        if t.count(anchor) != 1:
            raise PatchError(f"dispatch anchor not found exactly once (found {t.count(anchor)})")
        block = _frag(frag_dir, "dispatch_block.py")
        t = t.replace(anchor, f"        # {MARK_DISPATCH}\n" + block + "\n" + anchor, 1)
        changed.append("dispatch")

    return t, changed


def is_fully_patched(app_text: str) -> bool:
    return all(m in app_text for m in ALL_MARKERS)
