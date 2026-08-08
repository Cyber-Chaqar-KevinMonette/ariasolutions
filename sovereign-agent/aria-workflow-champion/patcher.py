"""patcher.py — Keys round K8: aria-workflow-champion.

Two anchored, idempotent patches (tools/__init__.py: import + __all__) +
one rich render for `workflow-designed-d` in run_surface.py. The
design_workflow tool itself is a NEW file (payload/), copied whole.

Deferred honestly, named not dropped: the WorkflowsScreen upgrade
(catalog → catalog + live drafts) — the drafts are durable JSON and
listable via `list_drafts()`; the screen work is UI polish for a future
pass, not load-bearing for the design→handoff→gated-execution loop.
"""
from __future__ import annotations

MARK = "workflow-champion-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


TOOLS_IMPORT_ANCHOR = (
    "from .platform_guide import PlatformGuideTool  # crossplatform-canon-d\n"
)
TOOLS_IMPORT_NEW = (
    TOOLS_IMPORT_ANCHOR
    + f"from .design_workflow import DesignWorkflowTool  # {MARK}\n"
)

TOOLS_ALL_ANCHOR = (
    '    "PlatformGuideTool",  # crossplatform-canon-d\n'
)
TOOLS_ALL_NEW = (
    TOOLS_ALL_ANCHOR
    + f'    "DesignWorkflowTool",  # {MARK}\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, TOOLS_IMPORT_ANCHOR, TOOLS_IMPORT_NEW, label="tools import anchor")
    text = _replace_once(text, TOOLS_ALL_ANCHOR, TOOLS_ALL_NEW, label="tools __all__ anchor")
    return text, True


SURFACE_ANCHOR = (
    '        if flag == "qa-start-d":\n'
)
SURFACE_NEW = (
    f'        if flag == "workflow-designed-d":  # {MARK}\n'
    "            return (f\"[cyan]◈ designed:[/cyan] {str(p.get('title', ''))[:50]} \"\n"
    "                    f\"[dim]({p.get('steps', '?')} steps — review + /work to run)[/dim]\")\n"
    '        if flag == "qa-start-d":\n'
)


def patch_run_surface(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SURFACE_ANCHOR, SURFACE_NEW, label="run_surface anchor")
    return text, True
