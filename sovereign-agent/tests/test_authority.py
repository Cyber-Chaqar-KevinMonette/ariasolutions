"""Authority gate tests. Architecture §7.

The test ensures that a Tier 2 tool is invisible in BUSY mode (not in available
list) AND raises AuthorityViolation if the dispatcher is asked to gate it.
"""
from __future__ import annotations

import pytest

from sovereign_agent.authority import (
    AuthorityViolation,
    ToolMeta,
    check_authority,
    register_tool,
    tools_available_in_mode,
)
from sovereign_agent.modes import Mode


@pytest.fixture
def registered_tools():
    """Register a set of fake tools across all tiers for the test."""
    register_tool(
        ToolMeta(
            name="t0_read",
            tier=0,
            description="read",
            failure_modes=("not_found",),
        )
    )
    register_tool(
        ToolMeta(
            name="t1_write",
            tier=1,
            description="write",
            failure_modes=("disk_full", "permission_denied"),
        )
    )
    register_tool(
        ToolMeta(
            name="t2_move",
            tier=2,
            description="move",
            failure_modes=("path_collision",),
        )
    )
    register_tool(
        ToolMeta(
            name="t3_push",
            tier=3,
            description="push",
            requires_approval=True,
            failure_modes=("network_error", "auth_required"),
        )
    )


def test_busy_excludes_tier2_and_tier3(registered_tools):
    available = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "t0_read" in available
    assert "t1_write" in available
    assert "t2_move" not in available
    assert "t3_push" not in available


def test_oneshot_includes_all_tiers(registered_tools):
    available = {m.name for m in tools_available_in_mode(Mode.ONESHOT)}
    assert {"t0_read", "t1_write", "t2_move", "t3_push"} <= available


def test_busy_dispatcher_refuses_tier2(registered_tools):
    with pytest.raises(AuthorityViolation):
        check_authority("t2_move", Mode.BUSY)


def test_oneshot_dispatcher_allows_tier2(registered_tools):
    meta = check_authority("t2_move", Mode.ONESHOT)
    assert meta.tier == 2


def test_tier3_must_declare_requires_approval():
    with pytest.raises(ValueError):
        register_tool(
            ToolMeta(
                name="bad_tier3",
                tier=3,
                description="oops",
                requires_approval=False,
                failure_modes=("error",),
            )
        )


def test_tool_must_declare_failure_modes():
    with pytest.raises(ValueError):
        register_tool(
            ToolMeta(
                name="undeclared_failures",
                tier=0,
                description="lazy",
                failure_modes=(),
            )
        )
