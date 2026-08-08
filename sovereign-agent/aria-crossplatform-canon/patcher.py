"""patcher.py — Keys round K7: aria-crossplatform-canon.

Two anchored, idempotent patches:
  1. tools/__init__.py — register PlatformGuideTool (import + __all__).
  2. aria_lm/data.py — the canon joins gather_corpus() (right after the
     lessons source, same front-of-parts priority region so her own
     trained mind grows on it).

The canon itself (knowledge/crossplatform/*.md — Linux, Windows, macOS,
Mobile, eternal traps, PLATFORM_STANDARDS) + platform_guide.py are NEW
files (payload/), copied whole.
"""
from __future__ import annotations

MARK = "crossplatform-canon-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


TOOLS_IMPORT_ANCHOR = (
    "from .tool_paging import RequestToolsTool  # tool-paging-d\n"
)
TOOLS_IMPORT_NEW = (
    TOOLS_IMPORT_ANCHOR
    + f"from .platform_guide import PlatformGuideTool  # {MARK}\n"
)

TOOLS_ALL_ANCHOR = (
    '    "RequestToolsTool",  # tool-paging-d\n'
)
TOOLS_ALL_NEW = (
    TOOLS_ALL_ANCHOR
    + f'    "PlatformGuideTool",  # {MARK}\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, TOOLS_IMPORT_ANCHOR, TOOLS_IMPORT_NEW, label="tools import anchor")
    text = _replace_once(text, TOOLS_ALL_ANCHOR, TOOLS_ALL_NEW, label="tools __all__ anchor")
    return text, True


DATA_ANCHOR = (
    "    # 2. Any caller-provided text files.\n"
)
DATA_NEW = (
    f"    # 1c. The cross-platform engineering canon — {MARK}: curated,\n"
    "    # dense, hers to train on. Same graceful degradation as lessons.\n"
    "    # Inserted at the FRONT (same truncation lesson as the lessons\n"
    "    # source: the distilled block can exceed max_chars on its own, and\n"
    "    # truncation keeps only the corpus start).\n"
    "    try:\n"
    "        from pathlib import Path as _P\n"
    "\n"
    '        _canon = _P(__file__).resolve().parent.parent / "knowledge" / "crossplatform"\n'
    "        if _canon.is_dir():\n"
    '            for _md in sorted(_canon.glob("*.md")):\n'
    '                parts.insert(0, _md.read_text(encoding="utf-8", errors="ignore"))\n'
    "    except Exception:\n"
    "        pass\n"
    "\n"
    "    # 2. Any caller-provided text files.\n"
)


def patch_data_py(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, DATA_ANCHOR, DATA_NEW, label="data.py corpus anchor")
    return text, True
