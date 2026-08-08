"""Regression guard: cockpit Textual subclasses must not shadow framework internals.

Born from a real bug (2026-06-22): the Apply Dashboard declared `self._running`
as its own "script is executing" flag. `_running` is a load-bearing attribute on
Textual's `MessagePump` (every Screen/Widget IS a MessagePump) — Textual sets it
True when the message pump goes live. The dashboard's `if not self._running`
close-guard therefore blocked *every* close path (button + Escape) silently.

This test AST-scans every class in src/sovereign_agent/cockpit/ that derives from
a Textual base and fails if it assigns to any reserved MessagePump/Widget private
attribute. The whole class of bug becomes impossible to reintroduce.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


# Textual base classes a cockpit class might subclass. Suffix match keeps this
# robust to new widget types without needing to import textual at collection time.
_TEXTUAL_BASE_SUFFIXES = (
    "Screen", "ModalScreen", "Widget", "Static", "Button", "Container",
    "Label", "Input", "RichLog", "Vertical", "Horizontal", "VerticalScroll",
    "DataTable", "Tree", "ListView", "ListItem", "TabbedContent", "TabPane",
)


def _reserved_attrs() -> set[str]:
    """The private attribute names Textual's MessagePump + Widget set on self."""
    from textual.message_pump import MessagePump
    from textual.widget import Widget

    attrs: set[str] = set()
    for cls in (MessagePump, Widget):
        try:
            src = inspect.getsource(cls.__init__)
        except (OSError, TypeError):
            continue
        attrs |= set(re.findall(r"self\.(_\w+)\s*[:=]", src))
    # The most dangerous footguns are flags a developer naturally reaches for.
    # Always include _running even if Textual refactors its __init__ text.
    attrs.add("_running")
    return attrs


def _cockpit_files() -> list[Path]:
    root = _repo_root() / "src" / "sovereign_agent" / "cockpit"
    return [p for p in root.glob("*.py") if ".bak" not in p.name]


def _is_textual_subclass(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if any(name.endswith(suf) for suf in _TEXTUAL_BASE_SUFFIXES):
            return True
    return False


def _self_attr_assignments(node: ast.ClassDef) -> list[tuple[str, int]]:
    """Return (attr_name, lineno) for every `self._x = ...` inside the class."""
    found: list[tuple[str, int]] = []
    for sub in ast.walk(node):
        targets = []
        if isinstance(sub, ast.Assign):
            targets = sub.targets
        elif isinstance(sub, ast.AnnAssign) and sub.value is not None:
            targets = [sub.target]
        for tgt in targets:
            if (
                isinstance(tgt, ast.Attribute)
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == "self"
                and tgt.attr.startswith("_")
            ):
                found.append((tgt.attr, sub.lineno))
    return found


def test_no_cockpit_class_shadows_textual_internals():
    reserved = _reserved_attrs()
    violations: list[str] = []

    for path in _cockpit_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_textual_subclass(node):
                continue
            for attr, lineno in _self_attr_assignments(node):
                if attr in reserved:
                    violations.append(
                        f"{path.name}:{lineno}  class {node.name} assigns "
                        f"self.{attr} — shadows a Textual MessagePump/Widget internal"
                    )

    assert not violations, (
        "Cockpit class shadows a Textual framework attribute (close-button-bug class):\n  "
        + "\n  ".join(violations)
        + "\n\nRename the offending flag (e.g. _running -> _script_running)."
    )


def test_reserved_set_includes_running():
    # Sanity: the guard must always cover the original offender.
    assert "_running" in _reserved_attrs()


def test_apply_screen_uses_script_running():
    # The original fix must stay in place.
    root = _repo_root()
    text = (root / "src" / "sovereign_agent" / "cockpit" / "apply_screen.py").read_text()
    assert "self._script_running" in text
    # And must NOT reintroduce the bare flag as code (comments may mention it).
    code_only = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    assert "self._running" not in code_only
