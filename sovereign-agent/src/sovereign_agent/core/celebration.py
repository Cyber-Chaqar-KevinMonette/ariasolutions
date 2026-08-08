"""
core/celebration.py — celebration message generator
v0.2.40 wholeness

Generates warm, contextual celebration messages for real milestones.
Template-based with optional LLM polish — runs without LLM dependency
so it works on day one. When LLM handlers are wired in later, swap the
template render for a values-prompted generation.

The warmth is structural, not performance: the templates know what
just happened, the user's name, and the milestone class. Generic
"congratulations!" never gets emitted.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sovereign_agent.core.values import AriaValues


class MilestoneType(str, Enum):
    FIRST_WORKFLOW = "first_workflow"
    TASK_COMPLETE = "task_complete"
    BUG_FIXED = "bug_fixed"
    SESSION_MILESTONE = "session_milestone"
    BIRTHDAY = "birthday"
    PROJECT_COMPLETE = "project_complete"


@dataclass
class CelebrationContext:
    milestone_type: MilestoneType
    user_name: str
    detail: str
    memory_context: str = ""


# Per-milestone templates. Multiple variants per type so messages don't
# feel repetitive across a session. Templates use {name} and {detail}
# substitutions. Tone matches "celebratory" register from values spec.
_TEMPLATES: dict[MilestoneType, list[str]] = {
    MilestoneType.FIRST_WORKFLOW: [
        "{name} — that's it. {detail}. First real workflow on the books.",
        "Beautiful work, {name}. {detail}. The skeleton walks for real now.",
        "{name}, that just happened. {detail}. First production workflow logged.",
    ],
    MilestoneType.TASK_COMPLETE: [
        "Task done, {name}: {detail}.",
        "{name} — {detail}. Clean completion.",
        "Done, {name}. {detail}.",
    ],
    MilestoneType.BUG_FIXED: [
        "{name} — caught it: {detail}.",
        "Bug fixed: {detail}. Good catch, {name}.",
        "{name}, {detail}. The doctor is honest again.",
    ],
    MilestoneType.SESSION_MILESTONE: [
        "{name}, milestone: {detail}.",
        "Notable, {name} — {detail}.",
    ],
    MilestoneType.BIRTHDAY: [
        "Happy birthday, {name}! {detail}",
        "{name} — happy birthday. {detail}",
    ],
    MilestoneType.PROJECT_COMPLETE: [
        "{name}, project complete: {detail}.",
        "That's it, {name}. {detail}. Project landed.",
    ],
}


def generate_celebration(
    ctx: CelebrationContext,
    values: Optional[AriaValues] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """Generate a celebration message.

    Values are accepted but optional — used by future LLM-polish path.
    rng is accepted for deterministic testing.
    """
    r = rng or random.Random()
    templates = _TEMPLATES.get(ctx.milestone_type, ["{name} — {detail}."])
    template = r.choice(templates)
    return template.format(name=ctx.user_name, detail=ctx.detail)


__all__ = [
    "MilestoneType", "CelebrationContext", "generate_celebration",
]
