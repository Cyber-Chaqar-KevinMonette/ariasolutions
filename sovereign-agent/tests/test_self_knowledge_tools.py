"""
test_self_knowledge_tools.py — tests for the self-knowledge and vessel-status tools.

Strategy: test each tool's execute() in isolation using mocks so no
Ollama, no SQLite, no sentinel filesystem, and no GPU are required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── ReadSelfTool ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_self_returns_kernel_fields():
    """ReadSelfTool output must contain all kernel sections."""
    from sovereign_agent.tools.self_knowledge import ReadSelfTool

    tool = ReadSelfTool()
    result = await tool.execute(tool.Args(), trace_id="t1")

    assert result.ok
    assert "Aria-Sovereign-V1" in result.output
    assert "Structure enough to channel" in result.output
    assert "commitments" in result.output.lower()
    assert "Voice" in result.output


@pytest.mark.asyncio
async def test_read_self_works_when_db_missing(tmp_path):
    """ReadSelfTool must succeed even if atoms.db doesn't exist."""
    from sovereign_agent.tools.self_knowledge import ReadSelfTool

    fake_settings = MagicMock()
    fake_settings.paths.atoms_db = tmp_path / "nonexistent.db"

    with patch("sovereign_agent.tools.self_knowledge.SETTINGS", fake_settings, create=True):
        tool = ReadSelfTool()
        result = await tool.execute(tool.Args(), trace_id="t2")

    assert result.ok
    assert "Aria-Sovereign-V1" in result.output


@pytest.mark.asyncio
async def test_read_self_includes_durable_state_when_available(tmp_path):
    """When atoms.db exists, durable state fields are included if non-empty."""
    import sqlite3
    from sovereign_agent.tools.self_knowledge import ReadSelfTool
    from sovereign_agent.aria import AriaState

    fake_state = AriaState(
        current_mood="focused",
        current_focus="building self-knowledge tools",
        active_goals=3,
    )

    def fake_load_state(conn):
        return fake_state

    db = tmp_path / "atoms.db"
    db.touch()

    fake_settings = MagicMock()
    fake_settings.paths.atoms_db = db

    with (
        patch("sovereign_agent.tools.self_knowledge.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.aria.load_state", fake_load_state),
    ):
        tool = ReadSelfTool()
        result = await tool.execute(tool.Args(), trace_id="t3")

    assert result.ok
    assert "focused" in result.output
    assert "building self-knowledge tools" in result.output


# ─── ListAvailableToolsTool ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_available_tools_returns_registered_tools():
    """ListAvailableToolsTool must return at least the built-in tools."""
    # Ensure the tool registry is populated by importing the tools package
    import sovereign_agent.tools  # noqa: F401 — side-effect import
    from sovereign_agent.tools.self_knowledge import ListAvailableToolsTool

    tool = ListAvailableToolsTool()
    result = await tool.execute(tool.Args(), trace_id="t4")

    assert result.ok
    assert "read_file" in result.output
    assert "memory_search" in result.output
    assert "list_available_tools" in result.output  # self-referential
    assert result.metadata.get("count", 0) >= 10


@pytest.mark.asyncio
async def test_list_available_tools_max_tier_filter():
    """max_tier=0 must return only Tier 0 tools."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.tools.self_knowledge import ListAvailableToolsTool

    tool = ListAvailableToolsTool()
    result = await tool.execute(tool.Args(max_tier=0), trace_id="t5")

    assert result.ok
    assert "write_file" not in result.output   # write_file is Tier 1+
    assert "Tier 0" in result.output


@pytest.mark.asyncio
async def test_list_available_tools_groups_by_tier():
    """Output must include Tier 0 and Tier 1 section headers."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.tools.self_knowledge import ListAvailableToolsTool

    tool = ListAvailableToolsTool()
    result = await tool.execute(tool.Args(), trace_id="t6")

    assert result.ok
    assert "Tier 0" in result.output
    assert "Tier 1" in result.output


# ─── ListSovCommandsTool ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sov_commands_calls_binary():
    """ListSovCommandsTool must invoke sovereign/sov and return output."""
    from sovereign_agent.tools.self_knowledge import ListSovCommandsTool

    mock_proc = MagicMock()
    mock_proc.stdout = "Usage: sovereign [OPTIONS] COMMAND\n  cockpit  Launch TUI\n"
    mock_proc.stderr = ""

    with (
        patch("sovereign_agent.tools.self_knowledge.shutil.which", return_value="/usr/bin/sovereign"),
        patch("sovereign_agent.tools.self_knowledge.subprocess.run", return_value=mock_proc),
    ):
        tool = ListSovCommandsTool()
        result = await tool.execute(tool.Args(), trace_id="t7")

    assert result.ok
    assert "cockpit" in result.output


@pytest.mark.asyncio
async def test_list_sov_commands_binary_not_found():
    """ListSovCommandsTool must fail gracefully if binary not on PATH."""
    from sovereign_agent.tools.self_knowledge import ListSovCommandsTool

    with patch("sovereign_agent.tools.self_knowledge.shutil.which", return_value=None):
        tool = ListSovCommandsTool()
        result = await tool.execute(tool.Args(), trace_id="t8")

    assert not result.ok
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_list_sov_commands_subcommand_help():
    """With subcommand set, sovereign <sub> --help is invoked."""
    from sovereign_agent.tools.self_knowledge import ListSovCommandsTool

    invocations: list[list[str]] = []

    def fake_run(argv, **kwargs):
        invocations.append(argv)
        m = MagicMock()
        m.stdout = "Usage: sovereign channels [OPTIONS]\n"
        m.stderr = ""
        return m

    with (
        patch("sovereign_agent.tools.self_knowledge.shutil.which", return_value="/usr/bin/sovereign"),
        patch("sovereign_agent.tools.self_knowledge.subprocess.run", side_effect=fake_run),
    ):
        tool = ListSovCommandsTool()
        result = await tool.execute(tool.Args(subcommand="channels"), trace_id="t9")

    assert result.ok
    assert invocations[0] == ["/usr/bin/sovereign", "channels", "--help"]


# ─── VesselStatusTool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vessel_status_returns_system_metrics():
    """VesselStatusTool must include CPU, RAM, disk, and uptime in output."""
    from sovereign_agent.tools.vessel_status import VesselStatusTool
    from sovereign_agent.cockpit.sysmon import SystemSnapshot
    from sovereign_agent.vram import VRAMSnapshot

    fake_snap = SystemSnapshot(
        cpu_percent=12.5,
        load_1m=0.45,
        load_5m=0.50,
        load_15m=0.55,
        cpu_count=8,
        mem_total=16 * 1024**3,
        mem_used=8 * 1024**3,
        mem_percent=50.0,
        mem_available=8 * 1024**3,
        disk_total=500 * 1024**3,
        disk_free=200 * 1024**3,
        disk_used=300 * 1024**3,
        disk_percent=60.0,
        uptime_seconds=86400,
    )
    fake_vram = VRAMSnapshot(total_mb=8192, used_mb=5750, free_mb=2442, source="nvml")

    fake_monitor = MagicMock()
    fake_monitor.read.return_value = fake_snap

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = None  # skip sentinels

    with (
        patch("sovereign_agent.tools.vessel_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.vessel_status.SystemMonitor", return_value=fake_monitor),
        patch("sovereign_agent.tools.vessel_status.read_vram", return_value=fake_vram),
    ):
        tool = VesselStatusTool()
        result = await tool.execute(tool.Args(include_sentinels=False), trace_id="t10")

    assert result.ok
    assert "12.5" in result.output   # cpu percent
    assert "8192" in result.output   # VRAM total
    assert "nvml" in result.output   # VRAM source


@pytest.mark.asyncio
async def test_vessel_status_includes_sentinel_health():
    """When sentinels are requested, their health status appears in output."""
    from sovereign_agent.tools.vessel_status import VesselStatusTool
    from sovereign_agent.cockpit.sysmon import SystemSnapshot
    from sovereign_agent.vram import VRAMSnapshot
    from sovereign_agent.stewardship.base import HealthStatus

    fake_snap = SystemSnapshot(cpu_percent=5.0, load_1m=0.1, load_5m=0.1, load_15m=0.1, cpu_count=4)
    fake_vram = VRAMSnapshot(total_mb=8192, used_mb=5750, free_mb=2442, source="estimate")
    fake_health = [
        HealthStatus(sentinel_id="cache", level="ok", summary="all good"),
        HealthStatus(sentinel_id="conformance", level="warning", summary="3 drift items"),
    ]

    from pathlib import Path
    fake_data_dir = Path("/fake/data")
    fake_settings = MagicMock()
    fake_settings.paths.data_dir = fake_data_dir

    with (
        patch("sovereign_agent.tools.vessel_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.vessel_status.SystemMonitor", return_value=MagicMock(read=MagicMock(return_value=fake_snap))),
        patch("sovereign_agent.tools.vessel_status.read_vram", return_value=fake_vram),
        patch("sovereign_agent.tools.vessel_status.gather_health", return_value=fake_health),
    ):
        tool = VesselStatusTool()
        result = await tool.execute(tool.Args(include_sentinels=True), trace_id="t11")

    assert result.ok
    assert "cache" in result.output
    assert "conformance" in result.output
    assert "drift items" in result.output


@pytest.mark.asyncio
async def test_vessel_status_survives_sysmon_failure():
    """VesselStatusTool must return a result even when sysmon raises."""
    from sovereign_agent.tools.vessel_status import VesselStatusTool
    from sovereign_agent.vram import VRAMSnapshot

    fake_vram = VRAMSnapshot(total_mb=8192, used_mb=5750, free_mb=2442, source="estimate")

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = None

    with (
        patch("sovereign_agent.tools.vessel_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.vessel_status.SystemMonitor", side_effect=RuntimeError("no /proc")),
        patch("sovereign_agent.tools.vessel_status.read_vram", return_value=fake_vram),
    ):
        tool = VesselStatusTool()
        result = await tool.execute(tool.Args(include_sentinels=False), trace_id="t12")

    # Should still return a result (partial) rather than raising
    assert result.output is not None
    assert "Errors" in result.output or "unavailable" in result.output
