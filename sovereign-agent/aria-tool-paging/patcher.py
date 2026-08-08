"""patcher.py — Keys round K5: aria-tool-paging.

Four anchored, idempotent patches:

loop.py (2):
  1. Unknown-tool refusals become HELPFUL: closest-name suggestions
     (difflib) + a request_tools pointer when the name exists in the
     registry but isn't currently attached. "REFUSED: unknown tool" was a
     dead end for a model one typo or one diet-trim away from the right
     call.
  2. After a successful request_tools call, the loop attaches the granted
     tools' schemas for the rest of the run — filtered through the SAME
     authority meta-list the loop was built from (paging can never smuggle
     a tool past the tier ceiling) and capped (MAX_PAGED_TOTAL) so the
     schema budget stays inside the context window. Emits `tool-paged-d`.

tools/__init__.py (1): register RequestToolsTool (import + __all__ in the
same patch — the recurring missing-__all__ bug class, preempted).

prompt_diet.py (1): "request_tools" joins CORE_TOOL_NAMES — the
discovery/attachment pair (list_available_tools + request_tools) must BOTH
always be visible or the pair is a dead end again.

tool_paging.py itself is a NEW file (payload/), copied whole.
"""
from __future__ import annotations

MARK = "tool-paging-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# loop.py
# ═══════════════════════════════════════════════════════════════════════

UNKNOWN_ANCHOR = (
    "                tool = tool_lookup.get(tool_name)\n"
    "                if tool is None:\n"
    "                    messages.append({\n"
    '                        "role": "tool", "name": tool_name,\n'
    '                        "content": "REFUSED: unknown tool",\n'
    "                    })\n"
    "                    continue\n"
)
UNKNOWN_NEW = (
    "                tool = tool_lookup.get(tool_name)\n"
    "                if tool is None:\n"
    f"                    # {MARK} — a dead-end refusal becomes a path forward:\n"
    "                    # suggest close names, and point at request_tools when\n"
    "                    # the tool exists but isn't currently attached.\n"
    "                    import difflib as _tp_difflib\n"
    "\n"
    "                    _tp_known = {m.name for m in available}\n"
    "                    if tool_name in _tp_known:\n"
    "                        _tp_msg = (\n"
    f'                            f"NOT ATTACHED: {{tool_name}} exists but its schema is "\n'
    f'                            f"not currently loaded — call request_tools([\'{{tool_name}}\']) "\n'
    '                            "to attach it, then call it again."\n'
    "                        )\n"
    "                    else:\n"
    "                        _tp_close = _tp_difflib.get_close_matches(\n"
    "                            tool_name, sorted(_tp_known | set(tool_lookup)), n=3,\n"
    "                        )\n"
    "                        _tp_msg = (\n"
    f'                            f"REFUSED: unknown tool {{tool_name!r}}."\n'
    f'                            + (f" Closest matches: {{_tp_close}}." if _tp_close else "")\n'
    '                            + " Use list_available_tools to discover, then"\n'
    '                            " request_tools([...]) to attach."\n'
    "                        )\n"
    "                    messages.append({\n"
    '                        "role": "tool", "name": tool_name,\n'
    '                        "content": _tp_msg,\n'
    "                    })\n"
    "                    continue\n"
)

PAGING_ANCHOR = (
    "                messages.append({\n"
    '                    "role": "tool", "name": tool_name, "content": content,\n'
    "                })\n"
    "\n"
    "            iter_count += 1\n"
)
PAGING_NEW = (
    "                messages.append({\n"
    '                    "role": "tool", "name": tool_name, "content": content,\n'
    "                })\n"
    "\n"
    f"                # {MARK} — request_tools grants: attach the granted\n"
    "                # schemas for the rest of the run. Filtered through the\n"
    "                # SAME authority meta-list this loop was built from —\n"
    "                # paging can never smuggle a tool past the tier ceiling —\n"
    "                # and capped so the schema budget stays sane.\n"
    '                if tool_name == "request_tools" and result.ok:\n'
    "                    try:\n"
    "                        from sovereign_agent.tools.tool_paging import MAX_PAGED_TOTAL\n"
    "\n"
    '                        _tp_granted = set((result.metadata or {}).get("granted", []))\n'
    "                        _tp_room = MAX_PAGED_TOTAL - max(0, len(available_tools) - _diet_tools_registered)\n"
    "                        _tp_added = [\n"
    "                            tools[m.name] for m in available\n"
    "                            if m.name in _tp_granted and m.name in tools\n"
    "                            and m.name not in tool_lookup\n"
    "                        ][:max(0, _tp_room)]\n"
    "                        if _tp_added:\n"
    "                            available_tools = available_tools + _tp_added\n"
    "                            schemas = [t.schema() for t in available_tools]\n"
    "                            tool_lookup = {t.name: t for t in available_tools}\n"
    '                            _record("tool-paged-d", {\n'
    '                                "added": [t.name for t in _tp_added],\n'
    '                                "active_total": len(available_tools),\n'
    "                            })\n"
    "                    except Exception:  # noqa: BLE001 — paging is an enhancement, never a breaker\n"
    "                        pass\n"
    "\n"
    "            iter_count += 1\n"
)


# The authority gate intercepts UNKNOWN names before tool dispatch (the
# registry lookup raises KeyError) — so typo suggestions must live in THAT
# branch; the NOT-ATTACHED branch below it only sees known, within-tier,
# not-currently-attached names. Found by the module's own live test run,
# not by inspection.
AUTHORITY_ANCHOR = (
    "                except (AuthorityViolation, KeyError) as e:\n"
    '                    _record("authority-x", {"tool": tool_name, "error": str(e)})\n'
    "                    messages.append({\n"
    '                        "role": "tool", "name": tool_name,\n'
    '                        "content": f"REFUSED: {e}",\n'
    "                    })\n"
    "                    continue\n"
)
AUTHORITY_NEW = (
    "                except (AuthorityViolation, KeyError) as e:\n"
    '                    _record("authority-x", {"tool": tool_name, "error": str(e)})\n'
    f"                    # {MARK} — a typo'd/unknown name lands HERE (registry\n"
    "                    # lookup raises KeyError): suggest close names so the\n"
    "                    # refusal is a path forward, not a dead end.\n"
    '                    _tp_hint = ""\n'
    "                    if isinstance(e, KeyError):\n"
    "                        import difflib as _tp_difflib\n"
    "\n"
    "                        _tp_close = _tp_difflib.get_close_matches(\n"
    "                            tool_name, sorted({m.name for m in available}), n=3,\n"
    "                        )\n"
    "                        if _tp_close:\n"
    "                            _tp_hint = (\n"
    '                                f" Closest matches: {_tp_close}."\n'
    '                                " Use request_tools([...]) to attach one."\n'
    "                            )\n"
    "                    messages.append({\n"
    '                        "role": "tool", "name": tool_name,\n'
    '                        "content": f"REFUSED: {e}{_tp_hint}",\n'
    "                    })\n"
    "                    continue\n"
)


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, AUTHORITY_ANCHOR, AUTHORITY_NEW, label="loop authority-hint anchor")
    text = _replace_once(text, UNKNOWN_ANCHOR, UNKNOWN_NEW, label="loop unknown-tool anchor")
    text = _replace_once(text, PAGING_ANCHOR, PAGING_NEW, label="loop paging anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# tools/__init__.py
# ═══════════════════════════════════════════════════════════════════════

TOOLS_IMPORT_ANCHOR = (
    "from .continual_learning_tools import ProposeRetrainTool  # continual-learning-d\n"
)
TOOLS_IMPORT_NEW = (
    TOOLS_IMPORT_ANCHOR
    + f"from .tool_paging import RequestToolsTool  # {MARK}\n"
)

TOOLS_ALL_ANCHOR = (
    '    "ProposeRetrainTool",  # continual-learning-d\n'
)
TOOLS_ALL_NEW = (
    TOOLS_ALL_ANCHOR
    + f'    "RequestToolsTool",  # {MARK}\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, TOOLS_IMPORT_ANCHOR, TOOLS_IMPORT_NEW, label="tools import anchor")
    text = _replace_once(text, TOOLS_ALL_ANCHOR, TOOLS_ALL_NEW, label="tools __all__ anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# prompt_diet.py — request_tools joins the always-visible core
# ═══════════════════════════════════════════════════════════════════════

DIET_ANCHOR = (
    "    # discovery — the model can always find the full surface\n"
    '    "list_available_tools",\n'
)
DIET_NEW = (
    "    # discovery + attachment — the pair must BOTH always be visible\n"
    f"    # or discovery is a dead end ({MARK})\n"
    '    "list_available_tools",\n'
    '    "request_tools",\n'
)


def patch_prompt_diet(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, DIET_ANCHOR, DIET_NEW, label="prompt_diet core anchor")
    return text, True
