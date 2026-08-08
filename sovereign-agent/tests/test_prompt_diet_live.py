"""Behavior tests for aria-prompt-diet, promoted to live tests/ — tests the
REAL, already-patched `sovereign_agent.prompt_diet` + `loop.py` directly.
Plain imports, no shadow copy.

The drift guard here is the load-bearing test: every ═══ section in the
live template MUST be classified, so a future section addition fails
loudly instead of silently bloating short-horizon prompts (or worse,
silently vanishing).
"""
from __future__ import annotations

import pytest


def _template() -> str:
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE

    return SYSTEM_PROMPT_TEMPLATE


# ── drift guards ──────────────────────────────────────────────────────────


def test_every_template_section_is_classified():
    from sovereign_agent import prompt_diet as pd

    _, sections = pd.split_sections(_template())
    names = {n for n, _ in sections}
    unclassified = names - pd.KEEP_ALWAYS - pd.DROP_FOR_SHORT_HORIZON
    assert unclassified == set(), (
        f"new template section(s) not classified in prompt_diet.py: {unclassified} — "
        "add each to KEEP_ALWAYS or DROP_FOR_SHORT_HORIZON deliberately"
    )


def test_every_classified_section_still_exists():
    """The reverse drift: a renamed/removed section leaves a stale entry."""
    from sovereign_agent import prompt_diet as pd

    _, sections = pd.split_sections(_template())
    names = {n for n, _ in sections}
    stale = (pd.KEEP_ALWAYS | pd.DROP_FOR_SHORT_HORIZON) - names
    assert stale == set(), f"classified sections no longer in the template: {stale}"


def test_every_core_tool_name_exists_in_registry():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent import prompt_diet as pd
    from sovereign_agent.authority import _TIER_REGISTRY

    missing = sorted(pd.CORE_TOOL_NAMES - set(_TIER_REGISTRY))
    assert missing == [], f"CORE_TOOL_NAMES not in the live registry: {missing}"


# ── section diet ──────────────────────────────────────────────────────────


def test_split_round_trips_byte_identical():
    from sovereign_agent import prompt_diet as pd

    pre, sections = pd.split_sections(_template())
    assert pre + "".join(t for _, t in sections) == _template()


def test_kill_switch_yields_byte_identical_output(monkeypatch):
    from sovereign_agent import prompt_diet as pd

    monkeypatch.setenv(pd.KILL_SWITCH_ENV, "1")
    assert pd.render(_template(), "oneshot") == _template()


def test_long_horizon_modes_get_the_full_template():
    from sovereign_agent import prompt_diet as pd

    for mode in ("timed", "until"):
        assert pd.render(_template(), mode) == _template()


def test_short_horizon_renders_under_budget():
    from sovereign_agent import prompt_diet as pd

    for mode in ("oneshot", "busy"):
        out = pd.render(_template(), mode)
        assert len(out) < 14_000, f"{mode} render too large: {len(out)} chars"


def test_safety_gate_sections_survive_every_mode():
    """The gates are never dieted: AUTONOMY (kernel hard limits),
    UNTRUSTED INPUT, MODE AWARENESS, PLAN APPROVAL stay in every render."""
    from sovereign_agent import prompt_diet as pd

    for mode in ("oneshot", "busy", "timed", "until"):
        out = pd.render(_template(), mode)
        for gate in ("═══ AUTONOMY ═══", "═══ UNTRUSTED INPUT DOCTRINE ═══",
                     "═══ MODE AWARENESS ═══", "═══ PLAN APPROVAL ═══"):
            assert gate in out, f"{gate} missing from {mode} render"


def test_format_placeholders_survive_every_render():
    from sovereign_agent import prompt_diet as pd

    for mode in ("oneshot", "busy", "timed", "until"):
        out = pd.render(_template(), mode)
        assert "{mode_name}" in out
        assert "{tier_ceiling}" in out
        # and it actually formats without KeyError
        out.format(mode_name="X", tier_ceiling=1)


def test_rendered_system_prompt_via_loop_for_every_mode():
    """End to end through the real _system_prompt for every Mode value."""
    from sovereign_agent.loop import _system_prompt
    from sovereign_agent.modes import Mode

    for mode in Mode:
        p = _system_prompt(mode)
        assert len(p) > 1000
        assert mode.value.upper() in p


# ── tool-schema diet ──────────────────────────────────────────────────────


class _FakeTool:
    def __init__(self, name):
        self.name = name


def test_select_tools_keeps_core_and_drops_rest():
    from sovereign_agent import prompt_diet as pd

    tools = [_FakeTool("read_file"), _FakeTool("browser_navigate"), _FakeTool("run_shell")]
    kept = pd.select_tools(tools, goal="do something", mode_value="oneshot")
    names = {t.name for t in kept}
    assert names == {"read_file", "run_shell"}


def test_goal_mentioned_tool_is_always_added_back():
    """Ask for a tool by name, you get it — even outside the core set."""
    from sovereign_agent import prompt_diet as pd

    tools = [_FakeTool("read_file"), _FakeTool("foresight_14gen")]
    kept = pd.select_tools(
        tools, goal="Use the foresight_14gen tool on this plan", mode_value="oneshot",
    )
    assert {t.name for t in kept} == {"read_file", "foresight_14gen"}


def test_schema_diet_applies_to_long_horizon_modes_too():
    """Unlike the section diet, select_tools applies in EVERY mode — the
    full 213-schema blob (~40K tokens) exceeds even the 16K num_ctx the
    long-horizon models get; 'send everything' just truncated."""
    from sovereign_agent import prompt_diet as pd

    tools = [_FakeTool("read_file"), _FakeTool("browser_navigate")]
    kept = pd.select_tools(tools, goal="g", mode_value="timed")
    assert {t.name for t in kept} == {"read_file"}


def test_kill_switch_gets_full_tool_list(monkeypatch):
    from sovereign_agent import prompt_diet as pd

    monkeypatch.setenv(pd.KILL_SWITCH_ENV, "1")
    tools = [_FakeTool("browser_navigate")]
    assert pd.select_tools(tools, goal="g", mode_value="oneshot") == tools


def test_never_returns_empty_from_nonempty():
    from sovereign_agent import prompt_diet as pd

    tools = [_FakeTool("some_tool_not_in_core")]
    assert pd.select_tools(tools, goal="g", mode_value="oneshot") == tools


def test_diet_only_removes_never_adds():
    """The authority invariant: select_tools output is always a subset of
    its input — the diet can never smuggle a tool past the tier gate."""
    from sovereign_agent import prompt_diet as pd

    tools = [_FakeTool(n) for n in ("read_file", "run_shell", "browser_navigate")]
    kept = pd.select_tools(tools, goal="use recall_chunk please", mode_value="oneshot")
    assert set(kept) <= set(tools)


# ── the CLI tool registry (the deepest catch of the round) ───────────────


def test_cli_registry_contains_the_whole_tool_surface():
    """_build_tools_for_mode was a hardcoded 15-tool dict for the project's
    whole life — read_lessons/run_shell/recall_chunk/vessel_status were
    never callable via `sov run` in any mode. Now it must carry (nearly)
    every registered tool."""
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode

    tools = _build_tools_for_mode(Mode.ONESHOT)
    assert len(tools) > 150, f"registry suspiciously small: {len(tools)}"
    for name in ("read_lessons", "run_shell", "recall_chunk", "vessel_status",
                 "read_file", "write_file", "edit_file", "list_available_tools"):
        assert name in tools, f"{name} missing from the loop registry"


def test_cli_registry_mode_aware_overlays_preserved():
    """write/edit/copy_file must still be constructed with mode=mode,
    exactly as the old dict did."""
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.modes import Mode

    tools = _build_tools_for_mode(Mode.BUSY)
    for name in ("write_file", "edit_file", "copy_file"):
        assert getattr(tools[name], "_mode", None) == Mode.BUSY


# ── the real token budget ─────────────────────────────────────────────────


def test_oneshot_prompt_plus_core_schemas_fit_the_8k_window():
    """The whole point: rendered oneshot prompt + core tool schemas must
    leave real room in the tool-use model's hard 8,192-token window."""
    import json

    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent import prompt_diet as pd
    from sovereign_agent.loop import _system_prompt
    from sovereign_agent.modes import Mode

    prompt_chars = len(_system_prompt(Mode.ONESHOT))

    from sovereign_agent.authority import _TIER_REGISTRY
    import inspect
    import sovereign_agent.tools as tools_pkg
    from sovereign_agent.tools.base import Tool

    registry = {}
    for name in dir(tools_pkg):
        obj = getattr(tools_pkg, name)
        if inspect.isclass(obj) and issubclass(obj, Tool) and obj is not Tool:
            try:
                inst = obj()
                registry[inst.name] = inst
            except Exception:
                continue
    core = [registry[n] for n in sorted(pd.CORE_TOOL_NAMES) if n in registry]
    schema_chars = len(json.dumps([t.schema() for t in core]))

    est_tokens = (prompt_chars + schema_chars) // 4
    assert est_tokens < 7000, (
        f"oneshot prompt ({prompt_chars} chars) + core schemas ({schema_chars} chars) "
        f"≈ {est_tokens} tokens — too close to the 8192 window"
    )
