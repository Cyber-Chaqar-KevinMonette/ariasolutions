"""Aria's core: values, narration, celebration, identity continuity."""
from sovereign_agent.core.values import AriaValues, KILL_SWITCH_ENV as VALUES_KILL_SWITCH
from sovereign_agent.core.prompt_builder import build_system_prompt, values_summary_line
from sovereign_agent.core.narration import ActionNarration, ActionClass
from sovereign_agent.core.celebration import (
    MilestoneType, CelebrationContext, generate_celebration,
)
from sovereign_agent.core.identity_check import check_continuity, ContinuityResult

__all__ = [
    "AriaValues",
    "build_system_prompt", "values_summary_line",
    "ActionNarration", "ActionClass",
    "MilestoneType", "CelebrationContext", "generate_celebration",
    "check_continuity", "ContinuityResult",
]
