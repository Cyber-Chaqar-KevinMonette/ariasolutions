"""
test_know_thyself.py — verify the KNOW THYSELF module.
Tests: aria_status tool, read_diagnosis_log tool, loop.py patches.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── loop.py tests ─────────────────────────────────────────────────────────────


def test_loop_system_prompt_has_know_thyself():
    """loop.py must contain the KNOW THYSELF boot sequence section."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "KNOW THYSELF" in SYSTEM_PROMPT_TEMPLATE, (
        "KNOW THYSELF section missing — run apply_know_thyself.sh"
    )
    assert "aria_status" in SYSTEM_PROMPT_TEMPLATE
    assert "boot sequence" in SYSTEM_PROMPT_TEMPLATE.lower()


def test_loop_system_prompt_has_your_world():
    """loop.py must contain the YOUR WORLD workspace map section."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "YOUR WORLD" in SYSTEM_PROMPT_TEMPLATE
    assert "read_file" in SYSTEM_PROMPT_TEMPLATE
    assert "list_dir" in SYSTEM_PROMPT_TEMPLATE
    assert "search_text" in SYSTEM_PROMPT_TEMPLATE


def test_loop_system_prompt_has_sentinel_health():
    """loop.py must contain the SENTINEL HEALTH guidance section."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "SENTINEL HEALTH" in SYSTEM_PROMPT_TEMPLATE


# ── tool registration tests ───────────────────────────────────────────────────


def test_aria_status_tool_registered():
    """AriaStatusTool must be in the authority registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "aria_status" in _TIER_REGISTRY
    assert _TIER_REGISTRY["aria_status"].tier == 0


def test_read_diagnosis_log_tool_registered():
    """ReadDiagnosisLogTool must be in the authority registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "read_diagnosis_log" in _TIER_REGISTRY
    assert _TIER_REGISTRY["read_diagnosis_log"].tier == 0


# ── aria_status tool tests ────────────────────────────────────────────────────


import pytest


@pytest.mark.asyncio
async def test_aria_status_returns_summary():
    """aria_status returns a non-empty summary string as output."""
    from sovereign_agent.tools.aria_status import AriaStatusTool

    # Mock all the heavy dependencies
    fake_settings = MagicMock()
    fake_settings.paths.data_dir = Path("/tmp/fake-data")
    fake_settings.paths.atoms_db = Path("/tmp/fake-data/atoms.db")

    with (
        patch("sovereign_agent.tools.aria_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.aria_status.SystemMonitor", side_effect=ImportError),
        patch("sovereign_agent.tools.aria_status.read_vram", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.gather_health", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.SessionStore", side_effect=ImportError, create=True),
    ):
        tool = AriaStatusTool()
        result = await tool.execute(tool.Args(), trace_id="t1")

    # Even with all subsystems failing, it should still succeed
    assert result.ok
    assert result.output  # summary line always present
    assert isinstance(result.metadata, dict)


@pytest.mark.asyncio
async def test_aria_status_metadata_structure():
    """aria_status metadata has expected top-level keys."""
    from sovereign_agent.tools.aria_status import AriaStatusTool

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = Path("/tmp/fake-data")
    fake_settings.paths.atoms_db = Path("/tmp/fake-data/atoms.db")

    with (
        patch("sovereign_agent.tools.aria_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.aria_status.SystemMonitor", side_effect=ImportError),
        patch("sovereign_agent.tools.aria_status.read_vram", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.gather_health", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.SessionStore", side_effect=ImportError, create=True),
    ):
        tool = AriaStatusTool()
        result = await tool.execute(tool.Args(), trace_id="t2")

    m = result.metadata
    assert "vessel" in m
    assert "kernel" in m
    assert "tools" in m
    assert "sentinels" in m
    assert "session" in m
    assert "workspace" in m
    assert "summary" in m


@pytest.mark.asyncio
async def test_aria_status_kernel_reads_aria_py():
    """aria_status includes kernel designation from aria.py."""
    from sovereign_agent.tools.aria_status import AriaStatusTool

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = Path("/tmp/fake-data")
    fake_settings.paths.atoms_db = Path("/tmp/fake-data/atoms.db")

    with (
        patch("sovereign_agent.tools.aria_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.aria_status.SystemMonitor", side_effect=ImportError),
        patch("sovereign_agent.tools.aria_status.read_vram", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.gather_health", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.SessionStore", side_effect=ImportError, create=True),
    ):
        tool = AriaStatusTool()
        result = await tool.execute(tool.Args(include_commitments=True), trace_id="t3")

    kernel = result.metadata.get("kernel", {})
    # Should have read from aria.py (no mocking of aria imports)
    assert "designation" in kernel
    assert "Aria" in kernel["designation"] or "aria" in kernel.get("designation", "").lower()


@pytest.mark.asyncio
async def test_aria_status_no_commitments_when_excluded():
    """include_commitments=False omits the commitments list."""
    from sovereign_agent.tools.aria_status import AriaStatusTool

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = Path("/tmp/fake-data")
    fake_settings.paths.atoms_db = Path("/tmp/fake-data/atoms.db")

    with (
        patch("sovereign_agent.tools.aria_status.SETTINGS", fake_settings, create=True),
        patch("sovereign_agent.tools.aria_status.SystemMonitor", side_effect=ImportError),
        patch("sovereign_agent.tools.aria_status.read_vram", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.gather_health", side_effect=ImportError, create=True),
        patch("sovereign_agent.tools.aria_status.SessionStore", side_effect=ImportError, create=True),
    ):
        tool = AriaStatusTool()
        result = await tool.execute(tool.Args(include_commitments=False), trace_id="t4")

    kernel = result.metadata.get("kernel", {})
    assert "commitments" not in kernel


# ── read_diagnosis_log tool tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_diagnosis_log_empty_catalog(tmp_path):
    """Returns graceful message when no conflicts are logged."""
    from sovereign_agent.tools.read_diagnosis_log import ReadDiagnosisLogTool

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = tmp_path

    with patch("sovereign_agent.tools.read_diagnosis_log.SETTINGS", fake_settings, create=True):
        tool = ReadDiagnosisLogTool()
        result = await tool.execute(tool.Args(), trace_id="t5")

    assert result.ok
    assert "empty" in result.output.lower() or "no" in result.output.lower()


@pytest.mark.asyncio
async def test_read_diagnosis_log_unknown_case(tmp_path):
    """Returns error for an unknown case_id."""
    from sovereign_agent.tools.read_diagnosis_log import ReadDiagnosisLogTool

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = tmp_path
    (tmp_path / "diagnoses").mkdir()

    with patch("sovereign_agent.tools.read_diagnosis_log.SETTINGS", fake_settings, create=True):
        tool = ReadDiagnosisLogTool()
        result = await tool.execute(
            tool.Args(case_id="NONEXISTENT-001"), trace_id="t6"
        )

    assert not result.ok
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_read_diagnosis_log_lists_cases(tmp_path):
    """Reads and formats real catalog entries."""
    from sovereign_agent.tools.read_diagnosis_log import ReadDiagnosisLogTool
    from sovereign_agent.diagnosis import ConflictCatalog

    # Create a real conflict in the catalog
    catalog = ConflictCatalog(tmp_path)
    conflict = catalog.open_conflict(
        type="drift",
        trigger_event="something broke during testing",
        actor="claude",
    )
    catalog.diagnose(
        conflict.case_id,
        symptom_vs_cause="test passed but prod failed",
        root_cause="mock divergence",
        confidence=0.9,
        actor="claude",
    )

    fake_settings = MagicMock()
    fake_settings.paths.data_dir = tmp_path

    with patch("sovereign_agent.tools.read_diagnosis_log.SETTINGS", fake_settings, create=True):
        tool = ReadDiagnosisLogTool()
        result = await tool.execute(tool.Args(limit=5), trace_id="t7")

    assert result.ok
    assert "drift" in result.output
    assert "something broke" in result.output
    assert result.metadata["count"] >= 1
