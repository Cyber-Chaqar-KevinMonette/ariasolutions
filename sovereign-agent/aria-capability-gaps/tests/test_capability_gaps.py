"""
test_capability_gaps.py — first real test_router.py for sovereign-agent.

Tests the capability-gap enhancements:
  1. validate_command returns known subcommands in the reason for unknown subs
  2. _safe_alternatives fuzzy-matches real sov subcommands
  3. Router emits capability-gap-d event for unknown sov subcommands
  4. Known sov subcommands still validate correctly
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ─── validate_command ────────────────────────────────────────────────────────

def test_validate_command_known_tier0_passes():
    from sovereign_agent.router import validate_command
    ok, reason, tier = validate_command("sov status")
    assert ok
    assert tier == 0


def test_validate_command_known_tier1_passes():
    from sovereign_agent.router import validate_command
    ok, reason, tier = validate_command("sov backup snapshot")
    assert ok
    assert tier == 1


def test_validate_command_unknown_sub_fails_with_suggestions():
    """Unknown subcommand must fail and include the list of known subcommands."""
    from sovereign_agent.router import validate_command
    ok, reason, tier = validate_command("sov synthesize-report")
    assert not ok
    assert tier == 3
    # After the patch, reason should include known subcommands
    assert "known:" in reason or "status" in reason


def test_validate_command_blocked_token_fails():
    from sovereign_agent.router import validate_command
    ok, reason, tier = validate_command("sov status && rm -rf /")
    assert not ok
    assert tier == 3


def test_validate_command_shell_chaining_blocked():
    from sovereign_agent.router import validate_command
    ok, reason, tier = validate_command("sov status; echo pwned")
    assert not ok


# ─── _safe_alternatives ──────────────────────────────────────────────────────

def test_safe_alternatives_fuzzy_matches_close_subcommand():
    """'sov statuz' (typo) should suggest 'sov status' via fuzzy match."""
    from sovereign_agent.router import _safe_alternatives
    from sovereign_agent.intents import Work

    intent = MagicMock(spec=Work)
    intent.project_hint = None
    alts = _safe_alternatives(intent, "sov statuz")
    # After patch, should contain "sov status" as a fuzzy match
    flat = " ".join(alts)
    assert "status" in flat


def test_safe_alternatives_includes_build_suggestion():
    """For a truly unknown command, alternatives should suggest building it."""
    from sovereign_agent.router import _safe_alternatives
    from sovereign_agent.intents import Work

    intent = MagicMock(spec=Work)
    intent.project_hint = None
    alts = _safe_alternatives(intent, "sov synthesize-report-x99")
    flat = " ".join(alts)
    assert "aria-" in flat or "build" in flat or "staging" in flat


def test_safe_alternatives_with_project_hint():
    """With a project hint, project-related alternatives appear."""
    from sovereign_agent.router import _safe_alternatives
    from sovereign_agent.intents import Work

    intent = MagicMock(spec=Work)
    intent.project_hint = "my-project"
    alts = _safe_alternatives(intent, "sov flibbertigibbet")
    flat = " ".join(alts)
    assert "my-project" in flat or "projects" in flat


# ─── Router: capability-gap event ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_router_emits_capability_gap_event_for_unknown_subcommand():
    """When an unknown sov subcommand is proposed, router emits capability-gap-d."""
    from sovereign_agent.router import Router
    from sovereign_agent.intents import Work

    events: list[dict] = []
    router = Router(event_sink=events.append)

    intent = Work(
        summary="synthesize the weekly report",
        commands=["sov synthesize-report"],
        project_hint="",
        authority_tier=0,
        rationale="test",
    )

    result = await router.route(intent)
    # Result should be ambiguous (not executed)
    assert result.kind == "ambiguous"
    # A capability-gap-d event must have been emitted
    gap_events = [e for e in events if e.get("kind") == "capability-gap-d"]
    assert len(gap_events) == 1, f"Expected 1 capability-gap event, got: {events}"
    assert "synthesize-report" in gap_events[0]["proposed_command"]


@pytest.mark.asyncio
async def test_router_does_not_emit_gap_event_for_blocked_token():
    """Blocked-token failures must NOT emit a capability-gap event."""
    from sovereign_agent.router import Router
    from sovereign_agent.intents import Work

    events: list[dict] = []
    router = Router(event_sink=events.append)

    intent = Work(
        summary="do something bad",
        commands=["sov status && rm -rf /"],
        project_hint="",
        authority_tier=0,
        rationale="test",
    )

    result = await router.route(intent)
    assert result.kind == "ambiguous"
    gap_events = [e for e in events if e.get("kind") == "capability-gap-d"]
    assert len(gap_events) == 0, "Blocked-token failures should not emit capability-gap"


@pytest.mark.asyncio
async def test_router_known_subcommand_no_gap_event():
    """Known sov subcommands must not trigger capability-gap events."""
    from sovereign_agent.router import Router
    from sovereign_agent.intents import Work

    events: list[dict] = []
    router = Router(event_sink=events.append)

    intent = Work(
        summary="check status",
        commands=["sov status"],
        project_hint="",
        authority_tier=0,
        rationale="test",
    )

    result = await router.route(intent)
    # Known command may succeed or be dispatched; no gap event
    gap_events = [e for e in events if e.get("kind") == "capability-gap-d"]
    assert len(gap_events) == 0
