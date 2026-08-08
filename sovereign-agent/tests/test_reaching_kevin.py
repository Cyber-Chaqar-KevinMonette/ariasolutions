"""Tests for reaching-kevin-d.

Kevin, 2026-07-25: "she said while working in auto she is trying to
reach out to team members but cannot directly reach out to them there
are no tools available... I just messaged her and said I am her team."
Root cause: send_to_human/read_inbox were always real, working tools --
nothing in the system prompt ever told her they exist or who to use them
for, so a long autonomous session had no grounding for "who do I ask."
"""
from __future__ import annotations

from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
from sovereign_agent.modes import Mode


def test_prompt_names_kevin_as_the_only_human_not_a_team():
    assert "There is no" in SYSTEM_PROMPT_TEMPLATE
    assert "team" in SYSTEM_PROMPT_TEMPLATE.lower()
    assert "send_to_human" in SYSTEM_PROMPT_TEMPLATE


def test_prompt_gives_explicit_options_instead_of_stalling():
    section_start = SYSTEM_PROMPT_TEMPLATE.index("REACHING KEVIN MID-TASK")
    section = SYSTEM_PROMPT_TEMPLATE[section_start:section_start + 1200]
    assert "Keep working on another pending subtask" in section
    assert "Wait briefly" in section
    assert "End the turn cleanly" in section


def test_section_is_classified_in_prompt_diet():
    from sovereign_agent import prompt_diet

    assert "REACHING KEVIN MID-TASK" in prompt_diet.DROP_FOR_SHORT_HORIZON
    assert "REACHING KEVIN MID-TASK" not in prompt_diet.KEEP_ALWAYS


def test_section_is_present_for_long_horizon_work_mode():
    from sovereign_agent.loop import _system_prompt

    prompt = _system_prompt(Mode.TIMED)
    assert "REACHING KEVIN MID-TASK" in prompt


def test_section_is_dropped_for_short_horizon_oneshot():
    from sovereign_agent.loop import _system_prompt

    prompt = _system_prompt(Mode.ONESHOT)
    assert "REACHING KEVIN MID-TASK" not in prompt
