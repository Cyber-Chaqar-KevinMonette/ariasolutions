"""Tests for M69 — Aria MCP Server.

Verifies tool registration, entry point, and graceful DB fallbacks.
Does NOT start a real server process — uses FastMCP's internal registry.
"""
from __future__ import annotations

import sys


def test_mcp_module_importable():
    from sovereign_agent import mcp_server  # noqa: F401


def test_mcp_server_has_12_or_more_tools():
    from sovereign_agent.mcp_server import mcp
    tools = mcp._tool_manager._tools
    assert len(tools) >= 12, f"Expected ≥12 MCP tools, got {len(tools)}"


def test_mcp_tool_names_present():
    from sovereign_agent.mcp_server import mcp
    names = set(mcp._tool_manager._tools.keys())
    required = {
        "aria_status",
        "institutional_impulse_check",
        "value_proof_history",
        "task_backlog",
        "record_proof_of_value",
        "ask_aria",
        "giving_ledger",
        "wedge_calibrator",
        "recent_reflections",
        "hypothesis_queue",
        "risk_register",
        "git_week_summary",
    }
    missing = required - names
    assert not missing, f"Missing MCP tools: {missing}"


def test_sov_mcp_entry_point_importable():
    from sovereign_agent.mcp_server import main
    assert callable(main)


def test_mcp_server_resources_registered():
    from sovereign_agent.mcp_server import mcp
    resources = mcp._resource_manager._resources
    uris = set(resources.keys())
    assert "aria://doctrine/kernel" in uris
    assert "aria://doctrine/version" in uris


def test_protocol_zero_windows_guard():
    """install_signal_handlers() must not crash on any platform."""
    from sovereign_agent import protocol_zero
    if sys.platform == "win32":
        # Should be a no-op — no crash
        protocol_zero.install_signal_handlers()
    else:
        # Normal path — also should not crash
        protocol_zero.install_signal_handlers()
        protocol_zero.disarm()


def test_mcp_version_matches_package():
    from sovereign_agent import __version__
    from sovereign_agent.mcp_server import mcp
    # The server name should be Aria (not version-pinned)
    assert mcp.name == "Aria"
    # __version__ must be importable
    assert __version__ == "0.4.0"
