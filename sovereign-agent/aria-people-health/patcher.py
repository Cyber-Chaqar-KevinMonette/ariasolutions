"""patcher.py — People-Health round PH2: tool registration.

Patches tools/__init__.py to register RecordHealthFactTool — anchored on
the current tail import (peig_portrait_tool), idempotent.
"""
from __future__ import annotations

MARK = "health-record-import-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


IMPORT_ANCHOR = (
    "from .peig_portrait_tool import PEIGPortraitTool  # peig-portrait-import-d\n"
)

IMPORT_NEW = (
    IMPORT_ANCHOR
    + f"from .health_record_tool import RecordHealthFactTool  # {MARK}\n"
)

ALL_ANCHOR = '    "DesignWorkflowTool",  # workflow-champion-d\n]'

ALL_NEW = f'    "DesignWorkflowTool",  # workflow-champion-d\n    "RecordHealthFactTool",  # {MARK}\n]'


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, IMPORT_ANCHOR, IMPORT_NEW, label="tools/__init__.py import")
    text = _replace_once(text, ALL_ANCHOR, ALL_NEW, label="tools/__init__.py __all__")
    return text, True


ALL_PATCHES = {
    "tools/__init__.py": patch_tools_init,
}
