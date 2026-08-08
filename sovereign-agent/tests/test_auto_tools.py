"""Tests for game-studio-d Part 2 — StartAutoTool's description gains
Kevin's own self-service rule (tier>=3 + concrete scoped goal = call it
herself), text only. Full behavioral coverage of start_auto/stop_auto
already lives in tests/test_auto_crown.py and is untouched by this
change — deliberately not duplicated here."""
from __future__ import annotations


def test_start_auto_description_states_the_self_service_rule():
    from sovereign_agent.tools.auto_tools import StartAutoTool
    desc = StartAutoTool.description
    assert "you may call this yourself" in desc.lower()
    assert ">=3" in desc or "tier is already" in desc.lower()
    assert "never call this to invent new work" in desc.lower()


def test_start_auto_tier_and_approval_semantics_unchanged():
    """The change is text-only — tier, requires_approval, and
    failure_modes must be exactly what they were before."""
    from sovereign_agent.tools.auto_tools import StartAutoTool
    assert StartAutoTool.tier == 2
    assert StartAutoTool.requires_approval is False
    assert "trust_tier_exceeded" in StartAutoTool.failure_modes


def test_stop_auto_untouched_still_tier_1_no_approval():
    """auto->plan stays free/instant — nothing here should have touched it."""
    from sovereign_agent.tools.auto_tools import StopAutoTool
    assert StopAutoTool.tier == 1
    assert StopAutoTool.requires_approval is False
