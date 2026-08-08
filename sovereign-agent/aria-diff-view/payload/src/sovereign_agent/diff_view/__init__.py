"""diff_view — show what code Aria edits: green-add / red-remove (F12).

Kevin (2026-07-19): "when she works on files and writes code, any NL
terminal AI system should SHOW what code the AI is editing, Claude-Code-
tier or above. Green for add, red for remove — or color it with the
active theme; make green/red the editable defaults, for customization."

Pure + deterministic: a unified diff between before/after text, rendered
as Rich-markup lines with per-line gutter marks. Three color modes:
  • "classic"  — green add / red remove (the defaults)
  • "theme"    — add→theme.success, remove→theme.error (active theme)
  • overrides  — <data>/diff_theme.json wins over the mode's defaults

Nothing here touches a file or the network; callers pass text in, get
renderable lines out. The edit path (F10 shell/file writes) emits a
DiffView per edit → the atelier pane renders it live → it's ledgered so
`sov reviews` can replay the exact diffs (the "or above" over Claude
Code: replayable + theme-customizable + shown before apply).
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["DiffColors", "DiffLine", "DiffView", "build_diff", "load_colors"]

# the editable defaults (Kevin's green/red)
DEFAULT_ADD = "green"
DEFAULT_REMOVE = "red"
DEFAULT_CONTEXT = "dim"
DEFAULT_HEADER = "cyan"


@dataclass(frozen=True)
class DiffColors:
    add: str = DEFAULT_ADD
    remove: str = DEFAULT_REMOVE
    context: str = DEFAULT_CONTEXT
    header: str = DEFAULT_HEADER

    @classmethod
    def from_theme(cls, theme) -> "DiffColors":
        """Map add→success, remove→error of the ACTIVE theme (Kevin's
        'color it with the active theme' option)."""
        return cls(
            add=getattr(theme, "success", DEFAULT_ADD) or DEFAULT_ADD,
            remove=getattr(theme, "error", DEFAULT_REMOVE) or DEFAULT_REMOVE,
            context=getattr(theme, "text_muted", DEFAULT_CONTEXT) or DEFAULT_CONTEXT,
            header=getattr(theme, "accent", DEFAULT_HEADER) or DEFAULT_HEADER,
        )

    def with_overrides(self, overrides: dict) -> "DiffColors":
        """Editable overrides win over any mode's defaults."""
        return DiffColors(
            add=str(overrides.get("add", self.add)),
            remove=str(overrides.get("remove", self.remove)),
            context=str(overrides.get("context", self.context)),
            header=str(overrides.get("header", self.header)),
        )


@dataclass(frozen=True)
class DiffLine:
    kind: str        # "add" | "remove" | "context" | "header"
    text: str
    old_no: int | None = None
    new_no: int | None = None

    def render(self, colors: DiffColors) -> str:
        color = {"add": colors.add, "remove": colors.remove,
                 "context": colors.context, "header": colors.header}[self.kind]
        gutter = {"add": "+", "remove": "-", "context": " ",
                  "header": "@"}[self.kind]
        return f"[{color}]{gutter} {self.text}[/{color}]"


@dataclass
class DiffView:
    path: str
    lines: list[DiffLine] = field(default_factory=list)
    added: int = 0
    removed: int = 0

    @property
    def is_empty(self) -> bool:
        return self.added == 0 and self.removed == 0

    def summary(self) -> str:
        if self.is_empty:
            return f"{self.path}: no changes"
        return f"{self.path}: [green]+{self.added}[/green] [red]-{self.removed}[/red]"

    def render(self, colors: DiffColors | None = None) -> list[str]:
        colors = colors or DiffColors()
        out = [f"[{colors.header}]▸ {self.path}[/{colors.header}]  {self.summary()}"]
        out.extend(ln.render(colors) for ln in self.lines)
        return out

    def to_ledger(self) -> dict:
        """A replayable record (the 'or above' over Claude Code)."""
        return {"path": self.path, "added": self.added, "removed": self.removed,
                "lines": [{"kind": l.kind, "text": l.text,
                           "old_no": l.old_no, "new_no": l.new_no}
                          for l in self.lines]}


def build_diff(path: str, before: str, after: str, *, context: int = 3) -> DiffView:
    """Unified diff of before→after. Binary/huge-safe: non-text falls back
    to a single header line rather than exploding."""
    view = DiffView(path=path)
    if "\x00" in (before or "") or "\x00" in (after or ""):
        view.lines.append(DiffLine("header", "(binary file — diff not shown)"))
        return view
    a = (before or "").splitlines()
    b = (after or "").splitlines()
    sm = difflib.SequenceMatcher(None, a, b)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            # keep only `context` lines at each edge of an equal block
            block = list(range(i1, i2))
            keep = set(block[:context]) | set(block[-context:]) if block else set()
            for k in sorted(keep):
                view.lines.append(DiffLine("context", a[k],
                                           old_no=k + 1, new_no=(j1 + (k - i1)) + 1))
            continue
        if tag in ("replace", "delete"):
            for k in range(i1, i2):
                view.lines.append(DiffLine("remove", a[k], old_no=k + 1))
                view.removed += 1
        if tag in ("replace", "insert"):
            for k in range(j1, j2):
                view.lines.append(DiffLine("add", b[k], new_no=k + 1))
                view.added += 1
    return view


def load_colors(data_dir: Path | None = None, *, mode: str = "classic",
                theme=None) -> DiffColors:
    """Resolve the color set: classic green/red OR active theme, then apply
    the editable <data>/diff_theme.json overrides on top (they always win)."""
    base = DiffColors.from_theme(theme) if (mode == "theme" and theme) else DiffColors()
    overrides: dict = {}
    if data_dir is not None:
        try:
            p = Path(data_dir) / "diff_theme.json"
            if p.is_file():
                overrides = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a bad override file never breaks the view
            overrides = {}
    return base.with_overrides(overrides) if overrides else base
