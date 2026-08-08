"""Tests for read_game_file / edit_game_file — path-safe game-project file
access. Real bug this closes: Aria guessed a wrong absolute path for
fire.gd instead of resolving it via project_slug, live 2026-08-03."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import GameProject, game_workspace_dir, save


def _make_project(tmp_path, name="Ember Keep"):
    """sandbox_dir=None (not tmp_path-based) is deliberate: ReadGameFileTool/
    EditGameFileTool always resolve via game_workspace_dir(slug,
    sandbox_dir=None) internally, same as godot_check/place_game_sprite —
    so the fixture must land wherever THAT resolves (SETTINGS.paths.
    sandbox_dir, already redirected to a tmp dir by the autouse conftest
    fixture), not a separately-invented tmp path, or the tool looks in a
    different place than the test wrote to."""
    save(GameProject(project_name=name), tmp_path)
    workspace = game_workspace_dir("ember-keep", sandbox_dir=None)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_read_game_file_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "read_game_file" in _TIER_REGISTRY
    assert _TIER_REGISTRY["read_game_file"].tier == 0


def test_edit_game_file_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "edit_game_file" in _TIER_REGISTRY
    assert _TIER_REGISTRY["edit_game_file"].tier == 1


@pytest.mark.asyncio
async def test_read_game_file_unknown_project(tmp_path):
    from sovereign_agent.tools.game_file_tools import ReadGameFileTool
    tool = ReadGameFileTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", relative_path="fire.gd"), trace_id="t1",
    )
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_read_game_file_resolves_real_path_without_guessing(tmp_path):
    """The whole point: caller never supplies an absolute path."""
    from sovereign_agent.tools.game_file_tools import ReadGameFileTool
    workspace = _make_project(tmp_path)
    (workspace / "fire.gd").write_text("extends Node2D\n", encoding="utf-8")

    tool = ReadGameFileTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ember-keep", relative_path="fire.gd"), trace_id="t2",
    )
    assert result.ok
    assert "extends Node2D" in result.output


@pytest.mark.asyncio
async def test_read_game_file_rejects_path_escape(tmp_path):
    from sovereign_agent.tools.game_file_tools import ReadGameFileTool
    _make_project(tmp_path)

    tool = ReadGameFileTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ember-keep", relative_path="../../../etc/passwd"),
        trace_id="t3",
    )
    assert not result.ok
    assert "path_escapes_workspace" in result.error


@pytest.mark.asyncio
async def test_edit_game_file_edits_real_file(tmp_path):
    from sovereign_agent.tools.game_file_tools import EditGameFileTool
    workspace = _make_project(tmp_path)
    (workspace / "fire.gd").write_text("var ember: float = 100.0\n", encoding="utf-8")

    tool = EditGameFileTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(
            project_slug="ember-keep",
            relative_path="fire.gd",
            old_str="var ember: float = 100.0",
            new_str="var ember: float = 50.0",
        ),
        trace_id="t4",
    )
    assert result.ok
    assert (workspace / "fire.gd").read_text(encoding="utf-8") == "var ember: float = 50.0\n"


@pytest.mark.asyncio
async def test_edit_game_file_rejects_path_escape(tmp_path):
    from sovereign_agent.tools.game_file_tools import EditGameFileTool
    _make_project(tmp_path)

    tool = EditGameFileTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(
            project_slug="ember-keep",
            relative_path="../../outside.txt",
            old_str="x",
            new_str="y",
        ),
        trace_id="t5",
    )
    assert not result.ok
    assert "path_escapes_workspace" in result.error


@pytest.mark.asyncio
async def test_edit_game_file_old_str_not_found(tmp_path):
    from sovereign_agent.tools.game_file_tools import EditGameFileTool
    workspace = _make_project(tmp_path)
    (workspace / "fire.gd").write_text("var ember: float = 100.0\n", encoding="utf-8")

    tool = EditGameFileTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(
            project_slug="ember-keep",
            relative_path="fire.gd",
            old_str="this string is not in the file",
            new_str="x",
        ),
        trace_id="t6",
    )
    assert not result.ok
    assert "old_str not found" in result.error
