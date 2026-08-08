"""
test_workout.py — verify the workout (Cosmic Gym finale) module.
"""
from __future__ import annotations

import pytest


def test_list_cockpit_commands_tool_registered():
    """ListCockpitCommandsTool must be in the authority registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "list_cockpit_commands" in _TIER_REGISTRY
    assert _TIER_REGISTRY["list_cockpit_commands"].tier == 0


def test_commands_data_is_non_empty():
    """The command table must have entries."""
    from sovereign_agent.tools.cockpit_commands import _COMMANDS
    assert len(_COMMANDS) >= 10
    for cmd, hint, desc in _COMMANDS:
        assert cmd
        assert desc


def test_commands_has_key_commands():
    """Boot, health, docs, diagnosis, commands are all present."""
    from sovereign_agent.tools.cockpit_commands import _COMMANDS
    names = {c[0] for c in _COMMANDS}
    for expected in ("boot", "health", "docs", "diagnosis", "halt", "quit"):
        assert expected in names, f"expected /{expected} in command table"


def test_category_headers_reference_real_commands():
    """Every category header key must match a real command name."""
    from sovereign_agent.tools.cockpit_commands import _COMMANDS, _CATEGORY_HEADERS
    names = {c[0] for c in _COMMANDS}
    for key in _CATEGORY_HEADERS:
        assert key in names, f"category header key {key!r} not in _COMMANDS"


@pytest.mark.asyncio
async def test_list_cockpit_commands_tool_execute():
    """Tool returns a non-empty formatted string."""
    from sovereign_agent.tools.cockpit_commands import ListCockpitCommandsTool

    tool = ListCockpitCommandsTool()
    result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.ok
    assert "/boot" in result.output
    assert "/health" in result.output
    assert "/commands" in result.output or "/cmds" in result.output
    assert "SELF-AWARENESS" in result.output
    assert result.metadata["count"] >= 10


@pytest.mark.asyncio
async def test_list_cockpit_commands_output_format():
    """Output has grouped sections and descriptions."""
    from sovereign_agent.tools.cockpit_commands import ListCockpitCommandsTool

    tool = ListCockpitCommandsTool()
    result = await tool.execute(tool.Args(), trace_id="t2")

    lines = result.output.splitlines()
    assert any("CLIPBOARD" in l for l in lines)
    assert any("SYSTEM" in l for l in lines)
    # Every command line starts with spaces + /
    cmd_lines = [l for l in lines if l.strip().startswith("/")]
    assert len(cmd_lines) >= 10


def test_welcome_banner_has_boot_hint():
    """app.py welcome banner must include the /boot hint."""
    import pathlib
    app_py = pathlib.Path(__file__).resolve()
    for _ in range(8):
        candidate = app_py.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if candidate.exists():
            text = candidate.read_text()
            assert "/boot" in text, "app.py welcome banner missing /boot hint"
            return
        app_py = app_py.parent
    # If we can't find app.py, that's a test environment issue — skip
    pytest.skip("app.py not found from test directory")
