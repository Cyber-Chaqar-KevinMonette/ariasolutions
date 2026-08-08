"""Tests for M85 flaw catalog — FlawReadTool + FlawUpdateTool.

Tests write/read roundtrip, filtering, status transitions, and idempotency.
No cockpit or Textual required. Uses a tmp catalog dir.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root")


_REPO = _repo_root()
_FLAW_TOOLS = (
    _REPO / "aria-flaw-catalog" / "payload" / "src"
    / "sovereign_agent" / "tools" / "flaw_tools.py"
)
_SEED_SCRIPT = (
    _REPO / "aria-flaw-catalog" / "payload" / "scripts" / "seed_flaws.py"
)


def _inject(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_flaw_module():
    """Prefer the installed package (post-apply); fall back to staging payload.

    Importing the staging file under the real module name triggers a circular
    import once tools/__init__.py has been patched to import flaw_tools — so
    once applied, we use the live module directly.
    """
    try:
        import sovereign_agent.tools.flaw_tools as live
        return live
    except Exception:
        return _inject("sovereign_agent.tools.flaw_tools", _FLAW_TOOLS)


_flaw_mod = _load_flaw_module()
_load_flaws   = _flaw_mod._load_flaws
_append_flaw  = _flaw_mod._append_flaw
_catalog_path = _flaw_mod._catalog_path


# ── Helpers ───────────────────────────────────────────────────────────────────


def _patch_data_dir(tmp_path: Path, monkeypatch):
    """Point SETTINGS.paths.data_dir at a tmp directory."""
    class _Paths:
        data_dir = tmp_path / "data"

    class _Settings:
        paths = _Paths()

    _Paths.data_dir.mkdir(parents=True, exist_ok=True)

    import sovereign_agent.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "SETTINGS", _Settings(), raising=False)
    return _Paths.data_dir


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_flaw_read_empty_catalog(tmp_path, monkeypatch):
    """Empty catalog → ok=True, flaws=[], count=0."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _flaw_mod.FlawReadTool()
    result = await tool.execute(tool.Args(), trace_id="t")
    assert result.ok
    assert result.output["count"] == 0
    assert result.output["flaws"] == []


@pytest.mark.anyio
async def test_flaw_update_creates_new_flaw(tmp_path, monkeypatch):
    """flaw_update with new flaw_id creates a record."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)
    tool = _flaw_mod.FlawUpdateTool()
    result = await tool.execute(tool.Args(
        flaw_id="FLAW-TEST-001",
        title="Test wall",
        kind="data_gap",
        severity="notable",
        description="A test flaw for testing.",
        actor="Claude",
        status="open",
    ), trace_id="t")
    assert result.ok
    assert result.output["flaw_id"] == "FLAW-TEST-001"

    # Should be readable
    flaws = _load_flaws(data_dir)
    assert "FLAW-TEST-001" in flaws
    assert flaws["FLAW-TEST-001"]["title"] == "Test wall"


@pytest.mark.anyio
async def test_flaw_read_returns_written_flaw(tmp_path, monkeypatch):
    """Write a flaw, read it back via FlawReadTool."""
    _patch_data_dir(tmp_path, monkeypatch)
    update_tool = _flaw_mod.FlawUpdateTool()
    read_tool = _flaw_mod.FlawReadTool()

    await update_tool.execute(update_tool.Args(
        flaw_id="FLAW-002",
        title="Missing tool",
        kind="tool_missing",
        severity="critical",
        description="Tool X is missing.",
        actor="Kevin",
        status="open",
    ), trace_id="t")

    result = await read_tool.execute(read_tool.Args(), trace_id="t")
    assert result.ok
    assert result.output["count"] == 1
    assert result.output["open_critical"] == 1
    assert result.output["flaws"][0]["flaw_id"] == "FLAW-002"


@pytest.mark.anyio
async def test_flaw_filter_by_status(tmp_path, monkeypatch):
    """status= filter works correctly."""
    _patch_data_dir(tmp_path, monkeypatch)
    update_tool = _flaw_mod.FlawUpdateTool()
    read_tool = _flaw_mod.FlawReadTool()

    await update_tool.execute(update_tool.Args(
        flaw_id="FLAW-A", title="Open flaw", kind="data_gap",
        severity="watch", description=".", actor="Aria", status="open",
    ), trace_id="t")
    await update_tool.execute(update_tool.Args(
        flaw_id="FLAW-B", title="Resolved flaw", kind="data_gap",
        severity="watch", description=".", actor="Aria", status="resolved",
        resolution="Fixed it.",
    ), trace_id="t")

    open_result = await read_tool.execute(read_tool.Args(status="open"), trace_id="t")
    assert open_result.output["count"] == 1
    assert open_result.output["flaws"][0]["flaw_id"] == "FLAW-A"

    resolved_result = await read_tool.execute(read_tool.Args(status="resolved"), trace_id="t")
    assert resolved_result.output["count"] == 1
    assert resolved_result.output["flaws"][0]["flaw_id"] == "FLAW-B"


@pytest.mark.anyio
async def test_flaw_filter_by_severity(tmp_path, monkeypatch):
    """severity= filter returns only matching entries."""
    _patch_data_dir(tmp_path, monkeypatch)
    update_tool = _flaw_mod.FlawUpdateTool()
    read_tool = _flaw_mod.FlawReadTool()

    for flaw_id, sev in [("FLAW-X", "critical"), ("FLAW-Y", "notable"), ("FLAW-Z", "watch")]:
        await update_tool.execute(update_tool.Args(
            flaw_id=flaw_id, title=f"Flaw {sev}", kind="architecture",
            severity=sev, description=".", actor="Claude", status="open",
        ), trace_id="t")

    result = await read_tool.execute(read_tool.Args(severity="critical"), trace_id="t")
    assert result.output["count"] == 1
    assert result.output["flaws"][0]["flaw_id"] == "FLAW-X"


@pytest.mark.anyio
async def test_status_transition_open_to_resolved(tmp_path, monkeypatch):
    """Mark flaw resolved with resolution note."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _flaw_mod.FlawUpdateTool()

    await tool.execute(tool.Args(
        flaw_id="FLAW-T", title="Solvable flaw", kind="tool_missing",
        severity="notable", description=".", actor="Claude", status="open",
    ), trace_id="t")

    result = await tool.execute(tool.Args(
        flaw_id="FLAW-T", title="Solvable flaw", kind="tool_missing",
        severity="notable", description=".", actor="Claude",
        status="resolved", resolution="Built the missing tool in M85.",
    ), trace_id="t")

    assert result.ok
    assert result.output["status"] == "resolved"


@pytest.mark.anyio
async def test_resolved_without_resolution_rejected(tmp_path, monkeypatch):
    """status=resolved with empty resolution → invalid_status error."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _flaw_mod.FlawUpdateTool()

    result = await tool.execute(tool.Args(
        flaw_id="FLAW-BAD", title="Bad update", kind="data_gap",
        severity="watch", description=".", actor="Aria",
        status="resolved", resolution="",  # missing!
    ), trace_id="t")

    assert not result.ok
    assert "invalid_status" in result.error


@pytest.mark.anyio
async def test_invalid_status_rejected(tmp_path, monkeypatch):
    """Unknown status value → invalid_status error."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _flaw_mod.FlawUpdateTool()

    result = await tool.execute(tool.Args(
        flaw_id="FLAW-INV", title="x", kind="data_gap",
        severity="watch", description=".", actor="Aria", status="maybe",
    ), trace_id="t")

    assert not result.ok
    assert "invalid_status" in result.error


@pytest.mark.anyio
async def test_sort_critical_before_notable(tmp_path, monkeypatch):
    """Critical flaws sort before notable/watch in read output."""
    _patch_data_dir(tmp_path, monkeypatch)
    update_tool = _flaw_mod.FlawUpdateTool()
    read_tool = _flaw_mod.FlawReadTool()

    await update_tool.execute(update_tool.Args(
        flaw_id="FLAW-W", title="Watch", kind="data_gap",
        severity="watch", description=".", actor="Aria", status="open",
    ), trace_id="t")
    await update_tool.execute(update_tool.Args(
        flaw_id="FLAW-C", title="Critical", kind="architecture",
        severity="critical", description=".", actor="Kevin", status="open",
    ), trace_id="t")
    await update_tool.execute(update_tool.Args(
        flaw_id="FLAW-N", title="Notable", kind="tool_missing",
        severity="notable", description=".", actor="Claude", status="open",
    ), trace_id="t")

    result = await read_tool.execute(read_tool.Args(), trace_id="t")
    severities = [r["severity"] for r in result.output["flaws"]]
    assert severities == ["critical", "notable", "watch"]


@pytest.mark.anyio
async def test_append_only_history_preserved(tmp_path, monkeypatch):
    """Updating a flaw appends a new line; history stays in file."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)
    tool = _flaw_mod.FlawUpdateTool()

    await tool.execute(tool.Args(
        flaw_id="FLAW-H", title="History flaw", kind="data_gap",
        severity="watch", description="v1", actor="Aria", status="open",
    ), trace_id="t")
    await tool.execute(tool.Args(
        flaw_id="FLAW-H", title="History flaw", kind="data_gap",
        severity="notable", description="v2", actor="Aria", status="in_progress",
        solution_path="working on it",
    ), trace_id="t")

    path = _catalog_path(data_dir)
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2  # both versions preserved


@pytest.mark.anyio
async def test_seed_script_idempotent(tmp_path, monkeypatch):
    """Seed script writes 7 flaws; second run skips all."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)

    seed_spec = importlib.util.spec_from_file_location("seed_flaws_test", _SEED_SCRIPT)
    seed_mod = importlib.util.module_from_spec(seed_spec)
    sys.modules["seed_flaws_test"] = seed_mod
    seed_spec.loader.exec_module(seed_mod)

    # Redirect catalog path to our tmp dir
    seed_mod._get_catalog_path = lambda: _catalog_path(data_dir)
    seed_mod.main()

    path = _catalog_path(data_dir)
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 7  # 7 known flaws

    # Run again — should not add more lines
    seed_mod.main()
    lines2 = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines2) == 7
