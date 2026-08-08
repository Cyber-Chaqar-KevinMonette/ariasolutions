"""patcher.py — Workstream Gym #9: aria-prompt-diet.

Four anchored, idempotent patches to loop.py:
  1. `_system_prompt` routes the template through prompt_diet.render(mode)
     BEFORE .format() — the section diet.
  2. The initial tool-list build routes through prompt_diet.select_tools —
     the schema diet (measured: 213 schemas ≈ 40K tokens against the
     oneshot tool-use model's hard 8,192 context; the model literally
     never saw an untruncated request).
  3. A `prompt-diet-d` event right after the messages are built — one
     observable record per run of what was actually sent (tools sent vs
     registered, prompt chars).
  4. The mid-loop mode-switch site rebuilds the tool list — it must stay
     dieted through a switch too.

prompt_diet.py itself is a NEW file (payload/), copied whole by the apply
script. Kill switch SOV_NO_PROMPT_DIET=1 → byte-identical prompt AND the
full tool list.
"""
from __future__ import annotations

MARK = "prompt-diet-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# 1. section diet in _system_prompt
SYSPROMPT_ANCHOR = (
    "def _system_prompt(mode: Mode) -> str:\n"
    "    from .modes import MODE_TIER_CEILING\n"
    "\n"
    "    return SYSTEM_PROMPT_TEMPLATE.format(\n"
)
SYSPROMPT_NEW = (
    "def _system_prompt(mode: Mode) -> str:\n"
    "    from .modes import MODE_TIER_CEILING\n"
    f"    from .prompt_diet import render as _diet_render  # {MARK}\n"
    "\n"
    "    return _diet_render(SYSTEM_PROMPT_TEMPLATE, mode.value).format(\n"
)

# 2. schema diet at the initial tool-list build
TOOLS_ANCHOR = (
    "    available = tools_available_in_mode(mode)\n"
    "    available_tools = [tools[m.name] for m in available if m.name in tools]\n"
    "    schemas = [t.schema() for t in available_tools]\n"
    "    tool_lookup = {t.name: t for t in available_tools}\n"
)
TOOLS_NEW = (
    "    available = tools_available_in_mode(mode)\n"
    "    available_tools = [tools[m.name] for m in available if m.name in tools]\n"
    f"    _diet_tools_registered = len(available_tools)  # {MARK}\n"
    "    from .prompt_diet import select_tools as _diet_select_tools\n"
    "    available_tools = _diet_select_tools(available_tools, goal=goal, mode_value=mode.value)\n"
    "    schemas = [t.schema() for t in available_tools]\n"
    "    tool_lookup = {t.name: t for t in available_tools}\n"
)

# 3. one observable record per run
EVENT_ANCHOR = (
    "        messages: list[dict[str, Any]] = [\n"
    '            {"role": "system", "content": _system_prompt(mode)},\n'
    '            {"role": "user", "content": goal},\n'
    "        ]\n"
)
EVENT_NEW = (
    "        messages: list[dict[str, Any]] = [\n"
    '            {"role": "system", "content": _system_prompt(mode)},\n'
    '            {"role": "user", "content": goal},\n'
    "        ]\n"
    f'        _record("prompt-diet-d", {{  # {MARK}\n'
    '            "tools_sent": len(available_tools),\n'
    '            "tools_registered": _diet_tools_registered,\n'
    '            "prompt_chars": len(messages[0]["content"]),\n'
    "        })\n"
)

# 4. the mid-loop mode-switch rebuild stays dieted
SWITCH_ANCHOR = (
    "                        available = tools_available_in_mode(mode)\n"
    "                        available_tools = [tools[m.name] for m in available if m.name in tools]\n"
    "                        schemas = [t.schema() for t in available_tools]\n"
)
SWITCH_NEW = (
    "                        available = tools_available_in_mode(mode)\n"
    "                        available_tools = [tools[m.name] for m in available if m.name in tools]\n"
    f"                        available_tools = _diet_select_tools(  # {MARK}\n"
    "                            available_tools, goal=goal, mode_value=mode.value,\n"
    "                        )\n"
    "                        schemas = [t.schema() for t in available_tools]\n"
)


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SYSPROMPT_ANCHOR, SYSPROMPT_NEW, label="loop _system_prompt anchor")
    text = _replace_once(text, TOOLS_ANCHOR, TOOLS_NEW, label="loop tools anchor")
    text = _replace_once(text, EVENT_ANCHOR, EVENT_NEW, label="loop event anchor")
    text = _replace_once(text, SWITCH_ANCHOR, SWITCH_NEW, label="loop mode-switch anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# cli.py — the deepest catch of the round: _build_tools_for_mode was a
# hardcoded 15-tool dict from the project's earliest days that silently
# never grew as ~200 tools were registered. The authority gate decides
# what a mode MAY see and the diet curates what is SENT — but a tool
# absent from this registry was invisible in every mode no matter what
# the gate allowed. read_lessons, run_shell, recall_chunk, vessel_status:
# none were ever callable via `sov run`.
# ═══════════════════════════════════════════════════════════════════════

CLI_ANCHOR = (
    "def _build_tools_for_mode(mode: Mode) -> dict:\n"
    "    from .tools import (\n"
    "        CopyFileTool, EditFileTool, EmbedQueryTool, ImageCaptionTool,\n"
    "        ImpactScoreTool, ListDirTool, MemorySearchTool, MemoryWriteTool,\n"
    "        PalaceSearchTool, ProposalWriteTool, ReadFileTool, SearchTextTool,\n"
    "        WebFetchTool, WebSearchTool, WriteFileTool, internet_available,\n"
    "    )\n"
    "    tools = {\n"
    '        "read_file": ReadFileTool(),\n'
    '        "list_dir": ListDirTool(),\n'
    '        "search_text": SearchTextTool(),\n'
    '        "embed_query": EmbedQueryTool(),\n'
    '        "image_caption": ImageCaptionTool(),\n'
    '        "web_fetch": WebFetchTool(),\n'
    '        "memory_search": MemorySearchTool(),\n'
    '        "memory_write": MemoryWriteTool(),\n'
    '        "palace_search": PalaceSearchTool(),\n'
    '        "proposal_write": ProposalWriteTool(),\n'
    '        "impact_score": ImpactScoreTool(),\n'
    '        "write_file": WriteFileTool(mode=mode),\n'
    '        "edit_file": EditFileTool(mode=mode),\n'
    '        "copy_file": CopyFileTool(mode=mode),\n'
    "    }\n"
    "    if internet_available():\n"
    '        tools["web_search"] = WebSearchTool()\n'
    "    return tools\n"
)
CLI_NEW = (
    "def _build_tools_for_mode(mode: Mode) -> dict:\n"
    f'    """Every registered Tool, instantiated — the loop\'s registry.  # {MARK}\n'
    "\n"
    "    This used to be a hardcoded 15-tool dict from the project's earliest\n"
    "    days; it silently never grew as ~200 tools were registered, so a\n"
    "    tool absent here was invisible in EVERY mode no matter what the\n"
    "    authority gate allowed. The gate (tools_available_in_mode) still\n"
    "    decides what a mode may see, and prompt_diet.select_tools curates\n"
    '    what is actually sent — this just stops silently losing the rest."""\n'
    "    import inspect as _inspect\n"
    "\n"
    "    from . import tools as _tools_pkg\n"
    "    from .tools import (\n"
    "        CopyFileTool, EditFileTool, WebSearchTool, WriteFileTool,\n"
    "        internet_available,\n"
    "    )\n"
    "    from .tools.base import Tool as _Tool\n"
    "\n"
    "    tools: dict = {}\n"
    "    for _name in dir(_tools_pkg):\n"
    "        _obj = getattr(_tools_pkg, _name)\n"
    "        if not (_inspect.isclass(_obj) and issubclass(_obj, _Tool) and _obj is not _Tool):\n"
    "            continue\n"
    "        try:\n"
    "            _inst = _obj()\n"
    "        except Exception:  # noqa: BLE001 — special-construction tools overlaid below\n"
    "            continue\n"
    "        tools[_inst.name] = _inst\n"
    "    # Mode-aware overlays — exactly the constructions the old dict used.\n"
    '    tools["write_file"] = WriteFileTool(mode=mode)\n'
    '    tools["edit_file"] = EditFileTool(mode=mode)\n'
    '    tools["copy_file"] = CopyFileTool(mode=mode)\n'
    "    if not internet_available():\n"
    '        tools.pop("web_search", None)\n'
    "    return tools\n"
)


def patch_cli(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, CLI_ANCHOR, CLI_NEW, label="cli _build_tools_for_mode anchor")
    return text, True
