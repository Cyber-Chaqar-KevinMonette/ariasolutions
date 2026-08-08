"""Tests for honor_log_read and honor_log_write tools (M79).

Pre-apply: injects staging honor_log_tool.py so tests can run before apply.

7 tests covering: empty ledger read, write+read roundtrip, invalid direction,
empty description, direction filter, tag filter, and append-only invariant.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ── Locate repo root (works from staging/ and from tests/ after apply) ────────

def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml found)")

_REPO = _repo_root()
_STAGING_TOOL = (
    _REPO / "aria-honor-calibration"
    / "payload" / "src" / "sovereign_agent" / "tools" / "honor_log_tool.py"
)


def _inject(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_honor_mod = _inject("sovereign_agent.tools.honor_log_tool", _STAGING_TOOL)
HonorLogReadTool = _honor_mod.HonorLogReadTool
HonorLogWriteTool = _honor_mod.HonorLogWriteTool


# ── Helpers ───────────────────────────────────────────────────────────────────


def _patch_ledger_path(tmp_path, monkeypatch):
    """Redirect the honor ledger to a tmp path."""
    from sovereign_agent.stewardship.honor import HonorLedger
    honor_path = tmp_path / "honor" / "ledger.jsonl"
    honor_path.parent.mkdir(parents=True, exist_ok=True)

    def _fake_ledger():
        return HonorLedger(honor_path)

    monkeypatch.setattr(_honor_mod, "_ledger", _fake_ledger)
    return honor_path


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_honor_log_read_empty_ledger(tmp_path, monkeypatch):
    """Empty ledger → ok=True, notes=[], count=0."""
    _patch_ledger_path(tmp_path, monkeypatch)

    tool = HonorLogReadTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["notes"] == []
    assert result.output["count"] == 0


@pytest.mark.asyncio
async def test_honor_log_write_and_read_roundtrip(tmp_path, monkeypatch):
    """Write said_no_correctly, read with direction filter → note returned."""
    _patch_ledger_path(tmp_path, monkeypatch)

    write_tool = HonorLogWriteTool()
    write_result = await write_tool.execute(
        write_tool.Args(
            direction="aria->self",
            category="said_no_correctly",
            description="Refused a request to skip safety tests.",
        ),
        trace_id="test",
    )
    assert write_result.ok is True
    note_id = write_result.output["note_id"]

    read_tool = HonorLogReadTool()
    read_result = await read_tool.execute(
        read_tool.Args(direction="aria->self"),
        trace_id="test",
    )

    assert read_result.ok is True
    assert read_result.output["count"] == 1
    note = read_result.output["notes"][0]
    assert note["note_id"] == note_id
    assert note["direction"] == "aria->self"
    assert "Refused" in note["text"]


@pytest.mark.asyncio
async def test_honor_log_write_invalid_direction(tmp_path, monkeypatch):
    """Invalid direction → ok=False, error mentions valid directions."""
    _patch_ledger_path(tmp_path, monkeypatch)

    tool = HonorLogWriteTool()
    result = await tool.execute(
        tool.Args(
            direction="aria->robot",
            category="safety_caught",
            description="Something happened.",
        ),
        trace_id="test",
    )

    assert result.ok is False
    assert "invalid_direction" in result.error
    assert "aria->self" in result.error or "aria->kevin" in result.error


@pytest.mark.asyncio
async def test_honor_log_write_empty_description(tmp_path, monkeypatch):
    """Empty description → ok=False, error mentions empty."""
    _patch_ledger_path(tmp_path, monkeypatch)

    tool = HonorLogWriteTool()
    result = await tool.execute(
        tool.Args(
            direction="aria->self",
            category="safety_caught",
            description="",
        ),
        trace_id="test",
    )

    assert result.ok is False
    assert "empty_description" in result.error or "empty" in result.error.lower()


@pytest.mark.asyncio
async def test_honor_log_read_direction_filter(tmp_path, monkeypatch):
    """Multiple directions → filtering by direction returns only matching notes."""
    _patch_ledger_path(tmp_path, monkeypatch)

    write_tool = HonorLogWriteTool()
    await write_tool.execute(
        write_tool.Args(direction="aria->self", category="said_no_correctly",
                        description="Caught a risk."),
        trace_id="test",
    )
    await write_tool.execute(
        write_tool.Args(direction="aria->kevin", category="value_given",
                        description="Kevin stayed patient."),
        trace_id="test",
    )
    await write_tool.execute(
        write_tool.Args(direction="aria->self", category="risk_flagged",
                        description="Flagged a hidden assumption."),
        trace_id="test",
    )

    read_tool = HonorLogReadTool()
    result = await read_tool.execute(read_tool.Args(direction="aria->self"), trace_id="test")

    assert result.ok is True
    assert result.output["count"] == 2
    for note in result.output["notes"]:
        assert note["direction"] == "aria->self"


@pytest.mark.asyncio
async def test_honor_log_read_tag_filter(tmp_path, monkeypatch):
    """Tag filter → only notes with that tag returned."""
    _patch_ledger_path(tmp_path, monkeypatch)

    write_tool = HonorLogWriteTool()
    await write_tool.execute(
        write_tool.Args(direction="aria->self", category="safety_caught",
                        description="Safety caught an issue."),
        trace_id="test",
    )
    await write_tool.execute(
        write_tool.Args(direction="aria->self", category="value_given",
                        description="Delivered real value."),
        trace_id="test",
    )

    read_tool = HonorLogReadTool()
    result = await read_tool.execute(read_tool.Args(tag="safety_caught"), trace_id="test")

    assert result.ok is True
    assert result.output["count"] == 1
    assert "safety_caught" in result.output["notes"][0]["tags"]


@pytest.mark.asyncio
async def test_honor_log_is_append_only(tmp_path, monkeypatch):
    """3 writes → exactly 3 lines in ledger.jsonl, none missing."""
    honor_path = _patch_ledger_path(tmp_path, monkeypatch)

    write_tool = HonorLogWriteTool()
    for i in range(3):
        await write_tool.execute(
            write_tool.Args(
                direction="aria->self",
                category="said_no_correctly",
                description=f"Integrity moment {i}",
            ),
            trace_id="test",
        )

    import json
    lines = [
        line.strip()
        for line in honor_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 3

    note_ids = {json.loads(line)["note_id"] for line in lines}
    assert len(note_ids) == 3, "All 3 notes should have unique IDs"
