"""
test_multi_step.py — verify the multi-step planning patch was applied.
"""
from __future__ import annotations


def test_loop_system_prompt_contains_planning_section():
    """The loop SYSTEM_PROMPT_TEMPLATE must contain the PLANNING section."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "═══ PLANNING ═══" in SYSTEM_PROMPT_TEMPLATE, (
        "PLANNING section not in loop.py — run apply_multi_step.sh"
    )


def test_loop_system_prompt_mentions_parallel_tool_calls():
    """Prompt must encourage parallel tool calls for independent work."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "tool_calls" in SYSTEM_PROMPT_TEMPLATE or "parallel" in SYSTEM_PROMPT_TEMPLATE.lower()


def test_loop_system_prompt_discourages_asking_permission():
    """Prompt must tell Aria not to ask permission for Tier 0/1."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "DO NOT ASK PERMISSION" in SYSTEM_PROMPT_TEMPLATE or "without permission" in SYSTEM_PROMPT_TEMPLATE.lower()


def test_per_subtask_budget_is_25():
    """The per-subtask iteration cap must be 25 (raised from 15)."""
    import inspect
    from sovereign_agent import agent_session
    src = inspect.getsource(agent_session)
    assert "max_iterations=25" in src, (
        "per-subtask cap still at 15 — run apply_multi_step.sh"
    )


def test_per_subtask_budget_15_is_gone():
    """The old 15-iteration cap must not appear in per-subtask budget context."""
    import inspect
    from sovereign_agent import agent_session
    src = inspect.getsource(agent_session)
    # The 15 should be replaced by 25 in the per_subtask_budget assignment
    # This is approximate — just check the overall structure improved
    assert "max_iterations=15, max_wall_seconds=600" not in src, (
        "old 15-iter cap still present — run apply_multi_step.sh"
    )
