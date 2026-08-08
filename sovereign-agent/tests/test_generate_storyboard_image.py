"""Tests for generate_storyboard_image — a thin wrapper composing the real
GenerateImageTool, scoped to a movie project's workspace.

Real GPU/diffusion calls are monkeypatched to a cheap fake throughout —
same reasoning as the capability-test menu's own tests: not safe or fast
enough for CI. `test_workflow_capability_tests.py`'s `create.image` test
already proves the real GenerateImageTool wiring works; this file proves
THIS tool's own composition/workspace-scoping logic on top of it.
"""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import MovieProject, save
from sovereign_agent.tools.generate_storyboard_image import GenerateStoryboardImageTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "generate_storyboard_image" in _TIER_REGISTRY
    assert _TIER_REGISTRY["generate_storyboard_image"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "generate_storyboard_image" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = GenerateStoryboardImageTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", prompt="a red cube"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_generation_failure_is_surfaced_not_swallowed(tmp_path, monkeypatch):
    from sovereign_agent.tools.image_generate import GenerateImageTool
    from sovereign_agent.tools.base import ToolResult

    save(MovieProject(title="Alpha"), tmp_path)

    async def fake_execute(self, args, *, trace_id):
        return ToolResult(ok=False, error="insufficient VRAM")
    monkeypatch.setattr(GenerateImageTool, "execute", fake_execute)

    tool = GenerateStoryboardImageTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", prompt="a red cube"), trace_id="t1")
    assert not result.ok
    assert "generation_failed" in result.error
    assert "insufficient VRAM" in result.error


@pytest.mark.asyncio
async def test_successful_generation_copies_into_workspace_and_records_asset(
        tmp_path, monkeypatch):
    from sovereign_agent.tools.image_generate import GenerateImageTool
    from sovereign_agent.tools.base import ToolResult

    save(MovieProject(title="Alpha"), tmp_path)

    fake_png = tmp_path / "fake_archive" / "12345_a_red_cube.png"
    fake_png.parent.mkdir(parents=True)
    fake_png.write_bytes(b"\x89PNG-fake-bytes")

    async def fake_execute(self, args, *, trace_id):
        return ToolResult(ok=True, output=str(fake_png))
    monkeypatch.setattr(GenerateImageTool, "execute", fake_execute)

    tool = GenerateStoryboardImageTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", prompt="a red cube"), trace_id="t1")
    assert result.ok

    from pathlib import Path
    dest = Path(result.output["path"])
    assert dest.is_file()
    assert dest.read_bytes() == b"\x89PNG-fake-bytes"
    assert dest.parent.name == "storyboards"
    # the shared archive copy is untouched (copy, not move)
    assert fake_png.is_file()

    manifest = (dest.parent.parent / "ASSET_MANIFEST.md").read_text(encoding="utf-8")
    assert dest.name in manifest
    assert "storyboard" in manifest
    assert "generate_storyboard_image" in manifest
