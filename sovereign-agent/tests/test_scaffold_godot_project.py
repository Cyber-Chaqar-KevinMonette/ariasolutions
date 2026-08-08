"""Tests for scaffold_godot_project — writes a real project.godot + starter
scene. The written files' actual validity against a real Godot binary was
confirmed manually (godot --headless --check-only --quit exits 0 for both
a Node2D and a Node3D scaffold) -- these tests cover the tool's own logic
(dimension routing, non-overwrite, unknown project) without needing a real
Godot binary in CI."""
from __future__ import annotations

import pytest

from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
from sovereign_agent.tools.scaffold_godot_project import ScaffoldGodotProjectTool


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "scaffold_godot_project" in _TIER_REGISTRY
    assert _TIER_REGISTRY["scaffold_godot_project"].tier == 1


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = ScaffoldGodotProjectTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_2d_project_gets_node2d_root(tmp_path):
    save(GameProject(project_name="Flat Runner", dimension="2d"), tmp_path)
    sandbox = tmp_path / "sandbox"
    tool = ScaffoldGodotProjectTool(data_dir=tmp_path)
    import sovereign_agent.tools.scaffold_godot_project as mod
    from unittest.mock import patch
    workspace = game_workspace_dir("flat-runner", sandbox_dir=sandbox)
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p):
        result = await tool.execute(tool.Args(project_slug="flat-runner"), trace_id="t1")
    assert result.ok
    assert result.output["root_node_type"] == "Node2D"
    scene = (workspace / "main.tscn").read_text()
    assert 'type="Node2D"' in scene
    project_godot = (workspace / "project.godot").read_text()
    assert 'config/name="Flat Runner"' in project_godot


@pytest.mark.asyncio
async def test_2_5d_project_also_gets_node2d_root(tmp_path):
    """2.5D is 2D gameplay with depth/perspective tricks on the same 2D
    node tree, not a different engine mode -- Godot's own convention."""
    save(GameProject(project_name="Iso Quest", dimension="2.5d"), tmp_path)
    sandbox = tmp_path / "sandbox"
    tool = ScaffoldGodotProjectTool(data_dir=tmp_path)
    import sovereign_agent.tools.scaffold_godot_project as mod
    from unittest.mock import patch
    workspace = game_workspace_dir("iso-quest", sandbox_dir=sandbox)
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p):
        result = await tool.execute(tool.Args(project_slug="iso-quest"), trace_id="t1")
    assert result.ok
    assert result.output["root_node_type"] == "Node2D"


@pytest.mark.asyncio
async def test_3d_project_gets_node3d_root(tmp_path):
    save(GameProject(project_name="Cube World", dimension="3d"), tmp_path)
    sandbox = tmp_path / "sandbox"
    tool = ScaffoldGodotProjectTool(data_dir=tmp_path)
    import sovereign_agent.tools.scaffold_godot_project as mod
    from unittest.mock import patch
    workspace = game_workspace_dir("cube-world", sandbox_dir=sandbox)
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p):
        result = await tool.execute(tool.Args(project_slug="cube-world"), trace_id="t1")
    assert result.ok
    assert result.output["root_node_type"] == "Node3D"
    scene = (workspace / "main.tscn").read_text()
    assert 'type="Node3D"' in scene


@pytest.mark.asyncio
async def test_never_overwrites_existing_project(tmp_path):
    save(GameProject(project_name="Already Built", dimension="2d"), tmp_path)
    sandbox = tmp_path / "sandbox"
    tool = ScaffoldGodotProjectTool(data_dir=tmp_path)
    import sovereign_agent.tools.scaffold_godot_project as mod
    from unittest.mock import patch
    workspace = game_workspace_dir("already-built", sandbox_dir=sandbox)
    (workspace / "project.godot").write_text("; real existing work, not a fixture")
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p):
        result = await tool.execute(tool.Args(project_slug="already-built"), trace_id="t1")
    assert not result.ok
    assert "already_scaffolded" in result.error
    # confirm it genuinely didn't touch the existing file
    assert (workspace / "project.godot").read_text() == "; real existing work, not a fixture"
