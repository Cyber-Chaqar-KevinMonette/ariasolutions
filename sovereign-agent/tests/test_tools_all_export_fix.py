"""Behavior tests for aria-tools-all-export-fix — prove every tool importable
from `sovereign_agent.tools` is also present in its `__all__`, and specifically
that the 6 tools found missing (calibration + honor-log + self-portrait) are
now exported. This is the seed test for J's future anchor-integrity scanner:
"a tool imported into __init__.py but absent from __all__ is invisible to
any __all__-based discovery" — a real bug this module fixes.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk upward until a `src/sovereign_agent/tools/__init__.py` is found —
    robust to this test running from its staged location (aria-<name>/tests/)
    or its final live location (tests/), which differ in nesting depth."""
    for candidate in (start, *start.parents):
        if (candidate / "src/sovereign_agent/tools/__init__.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
TOOLS_INIT = REPO_ROOT / "src/sovereign_agent/tools/__init__.py"

_PREVIOUSLY_MISSING = (
    "LogPredictionTool", "ResolvePredictionTool", "CalibrationLedgerTool",
    "HonorLogReadTool", "HonorLogWriteTool", "SelfPortraitTool",
)


def _parse_imported_and_all(source: str) -> tuple[set[str], list[str]]:
    """Return (names imported via `from .x import Y`, the __all__ list) by
    parsing the AST — no need to actually import the package."""
    tree = ast.parse(source)
    imported: set[str] = set()
    all_list: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant):
                                all_list.append(elt.value)
    return imported, all_list


def test_previously_missing_tools_are_now_exported():
    imported, all_list = _parse_imported_and_all(TOOLS_INIT.read_text(encoding="utf-8"))
    for name in _PREVIOUSLY_MISSING:
        assert name in imported, f"{name} should still be imported"
        assert name in all_list, f"{name} should now be in __all__"


def test_every_imported_tool_is_in_all():
    """The general form of the fix: no tool class imported via `from .x import Y`
    is missing from __all__. (Some non-Tool helper imports may legitimately be
    absent — this checks only names ending in 'Tool', matching the module's own
    naming convention.)"""
    imported, all_list = _parse_imported_and_all(TOOLS_INIT.read_text(encoding="utf-8"))
    tool_names = {n for n in imported if n.endswith("Tool")}
    missing = sorted(tool_names - set(all_list))
    assert missing == [], f"tools imported but not exported via __all__: {missing}"


def test_all_list_has_no_duplicates():
    _, all_list = _parse_imported_and_all(TOOLS_INIT.read_text(encoding="utf-8"))
    dupes = {n for n in all_list if all_list.count(n) > 1}
    assert dupes == set(), f"duplicate __all__ entries: {dupes}"
