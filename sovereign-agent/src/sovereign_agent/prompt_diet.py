"""prompt_diet.py — mode-aware sizing of what the model is sent, so the 8B
vessel can actually breathe.

Kill switch: SOV_NO_PROMPT_DIET=1 → byte-identical full template AND the
full tool list, exactly as before this module existed.

THE MEASURED PROBLEM (gym round, 2026-07-04 — found by the golden-reflex
gate failing honestly on its first run):
  - the system prompt is ~31,900 chars (~8K tokens), identical for every
    mode;
  - the 213 registered tool schemas serialize to ~160K chars (~40K tokens)
    and ride along with EVERY request;
  - the oneshot tool-use model (llama3-groq-tool-use:8b) has a hard 8,192
    context — `token-usage-d` showed prompt_tokens pinned at exactly 8192,
    17 junk completion tokens, `final_chars: 0`. The model wasn't
    struggling; it literally never saw an untruncated request.

TWO LEVERS, one module:
  1. Section diet — the template's `═══ NAME ═══` sections are classified
     (KEEP_ALWAYS / DROP_FOR_SHORT_HORIZON); short-horizon modes (ONESHOT,
     BUSY) drop the long-horizon/ambient crowns. The kernel-adjacent
     doctrine (AUTONOMY's hard limits, UNTRUSTED INPUT, MODE AWARENESS,
     PLAN APPROVAL...) is KEEP_ALWAYS — the safety gates are never dieted,
     in any mode. An UNCLASSIFIED new section is KEPT in every mode (safe
     default) and fails the drift-guard test loudly.
  2. Tool-schema diet — short-horizon modes send a curated CORE_TOOL_NAMES
     set (~31 tools, every name verified against the live registry by a
     test) PLUS any registered tool whose name appears verbatim in the
     goal text (ask for a tool by name, you get it). Long-horizon modes
     (TIMED/UNTIL) keep the full list — their model/config owns the
     larger-context tradeoff. `list_available_tools` is in the core set,
     so the model can always DISCOVER the full surface even when not every
     schema is attached.

AUTHORITY NOTE, stated plainly: the diet runs strictly INSIDE the
authority gate's output — it only ever REMOVES schemas from what
`tools_available_in_mode` already allowed, never adds. A model still
can't call what its tier withholds; this just stops drowning it in
schemas it wasn't going to need.
"""
from __future__ import annotations

import os
import re
from pathlib import Path  # noqa: F401 — kept for symmetry with sibling modules

KILL_SWITCH_ENV = "SOV_NO_PROMPT_DIET"

_HEADER_RE = re.compile(r"═══ ([^═\n]+?) ═══")

# ── Section classification ────────────────────────────────────────────────
# Every ═══ section in loop.py's SYSTEM_PROMPT_TEMPLATE must appear in
# exactly one of these two sets — the drift-guard test fails loudly on any
# unclassified addition. Unknown-at-runtime sections are KEPT (safe default).

KEEP_ALWAYS = frozenset({
    # identity / mode / the gates — never dieted, in any mode
    "ACTIVE MODE: {mode_name}",
    "MODE AWARENESS",
    "AUTONOMY",                      # carries the hard kernel limits
    "UNTRUSTED INPUT DOCTRINE",
    "PLAN APPROVAL",
    # working discipline a bounded task still needs
    "WHAT I HAVE LEARNED",
    "MEMORY",
    "PLANNING",
    "TERMINAL DISCIPLINE",
    "CONFIDENCE & DERIVATIVES",
    "ENGINEERING DOCTRINE",
    "RESILIENCE",
    "CACHE CROWN",
    "COMPRESSION ORACLE",            # recall_chunk guidance matters mid-task
    "DEEP REASONING — THINK BEFORE YOU ACT",
    "CODE AWARENESS",
    "EXECUTION & VERIFICATION",
    "COMPLETION",
})

DROP_FOR_SHORT_HORIZON = frozenset({
    # long-horizon / ambient / relationship crowns — real doctrine, wrong
    # audience for a single bounded `sov run` turn on an 8K-context model
    "PALACE MEMORY — WRITE ACCESS",
    "SELF-PERCEPTION — BEHAVIOR PATTERNS",
    "WEB RESEARCH",
    "PROVENANCE",
    "GIT WRITE (Tier 2 — operator confirmed)",
    "HONOR",
    "WORKFLOW MASTER",
    "BROWSER CROWN",
    "NOTIFY CROWN",
    "EVAL CROWN",
    "EXPERIENCE CROWN",
    "VOICE CROWN",
    "VISION CROWN",
    "EMOTION CROWN",
    "AUTO CROWN",
    "REACHING KEVIN MID-TASK",
    "RESUME CROWN",
    "LEVERAGE ORACLE",
    "COMPANION DOCTRINE",
    "THEORETICAL RESEARCHER",
    "VESSEL COMFORT",
    "OBJECTIVE MAP",
    "WORKFLOW",
    "KNOW THYSELF — BOOT SEQUENCE",
    "YOUR WORLD",
    "SENTINEL HEALTH",
})

# Modes that get the short-horizon diet. Mode values (Mode.value) are used
# so this module never imports modes.py at import time (loop.py imports us).
SHORT_HORIZON_MODES = frozenset({"oneshot", "busy"})

# ── Core tool set for short-horizon modes ─────────────────────────────────
# Every name is verified against the live registry by the drift-guard test.
# Sized to a real budget: prompt (~2.6K tokens) + these schemas + goal +
# generation must all fit the oneshot model's hard 8,192 window. Bigger
# siblings were deliberately dropped where a kept tool covers the need
# (retrieve_memory → memory_search/recall_chunk; run_command → run_shell;
# edit_in_place/copy_file → edit_file; notify → send_to_human). A tool
# named verbatim in the goal is always added back by select_tools, and
# list_available_tools lets the model discover the full surface.
CORE_TOOL_NAMES = frozenset({
    # files
    "read_file", "list_dir", "write_file", "edit_file",
    # execution
    "run_code", "run_shell", "run_tests",
    # memory / recall
    "read_lessons", "memory_search", "recall_chunk",
    # self / session
    "read_session", "aria_status", "vessel_status",
    # communication
    "read_inbox", "send_to_human", "acknowledge_inbox_note",
    # git (read-only)
    "git_status",
    # context management
    "context_stats",
    # discovery + attachment — the pair must BOTH always be visible
    # or discovery is a dead end (tool-paging-d)
    "list_available_tools",
    "request_tools",
})


def diet_enabled() -> bool:
    return not os.environ.get(KILL_SWITCH_ENV)


def split_sections(template: str) -> tuple[str, list[tuple[str, str]]]:
    """(preamble, [(canonical_section_name, full_section_text), ...]).

    full_section_text includes the header line, so re-joining preamble +
    all sections reproduces the template byte-for-byte."""
    parts = re.split(r"(═══ [^═\n]+? ═══[^\n]*\n)", template)
    preamble = parts[0]
    sections: list[tuple[str, str]] = []
    for i in range(1, len(parts), 2):
        header_line = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        name = _HEADER_RE.search(header_line).group(1).strip()
        sections.append((name, header_line + body))
    return preamble, sections


def render(template: str, mode_value: str) -> str:
    """The section diet. Returns the template with short-horizon drops
    applied — or byte-identical input when the kill switch is set, the
    mode is long-horizon, or anything at all goes wrong (never worse than
    the status quo)."""
    if not diet_enabled():
        return template
    if mode_value not in SHORT_HORIZON_MODES:
        return template
    try:
        preamble, sections = split_sections(template)
        kept = [
            text for name, text in sections
            if name not in DROP_FOR_SHORT_HORIZON  # unclassified → kept (safe)
        ]
        return preamble + "".join(kept)
    except Exception:  # noqa: BLE001 — a diet bug must never break the loop
        return template


def select_tools(available_tools: list, goal: str, mode_value: str) -> list:
    """The tool-schema diet. Filters the ALREADY-authority-gated tool list
    down to CORE_TOOL_NAMES plus any tool named verbatim in the goal.

    Applies to EVERY mode (unlike the section diet): the full 213-schema
    blob is ~40K tokens — beyond even the 16K num_ctx the long-horizon
    models get, so 'send everything' was never a real option in any mode;
    it just truncated. The kill switch returns the list untouched."""
    if not diet_enabled():
        return available_tools
    try:
        goal_lower = (goal or "").lower()
        kept = [
            t for t in available_tools
            if t.name in CORE_TOOL_NAMES or t.name in goal_lower
        ]
        # Never return an empty toolset from a non-empty one — if the core
        # set somehow matches nothing (renamed tools?), fall back whole.
        return kept if kept else available_tools
    except Exception:  # noqa: BLE001
        return available_tools


def measure(template: str, mode_value: str) -> dict:
    """Before/after numbers for the diet event + tests."""
    dieted = render(template, mode_value)
    return {
        "mode": mode_value,
        "chars_before": len(template),
        "chars_after": len(dieted),
        "est_tokens_before": len(template) // 4,
        "est_tokens_after": len(dieted) // 4,
        "enabled": diet_enabled(),
    }
