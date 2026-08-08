"""Tests for scan_game_project — read-only full-state refresh."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sovereign_agent import game_dev_xp
from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
from sovereign_agent.tools.scan_game_project import ScanGameProjectTool

import sovereign_agent.tools.scan_game_project as _mod


def _scaffold(tmp_path, project_name="Ember Keep", dimension="2d"):
    save(GameProject(project_name=project_name, dimension=dimension,
                     genre="idle-incremental", engine="godot",
                     concept="tend a dying fire"), tmp_path)
    slug = project_name.lower().replace(" ", "-")
    sandbox = tmp_path / "sandbox"
    workspace = game_workspace_dir(slug, sandbox_dir=sandbox)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "project.godot").write_text(f'config/name="{project_name}"\n')
    (workspace / "main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" path="res://fire.gd" id="1"]\n\n'
        '[node name="Main" type="Node2D"]\nscript = ExtResource("1")\n'
    )
    (workspace / "fire.gd").write_text("extends Node2D\n")
    (workspace / "GAME_BRIEF.md").write_text(
        "# Ember Keep\n\n## Design checklist\n- [ ] Core loop\n\n"
        "## Notes\n\n- 2026-08-02: scripted the core loop, not playtested yet.\n"
    )
    return slug, workspace


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = ScanGameProjectTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_scan_reports_real_file_tree_and_notes(tmp_path):
    slug, workspace = _scaffold(tmp_path)
    tool = ScanGameProjectTool(data_dir=tmp_path)
    with patch.object(_mod, "game_workspace_dir", return_value=workspace):
        result = await tool.execute(tool.Args(project_slug=slug), trace_id="t1")

    assert result.ok, result.error
    assert result.output["project_name"] == "Ember Keep"
    assert result.output["genre"] == "idle-incremental"
    assert "main.tscn" in result.output["file_tree"]
    assert "fire.gd" in result.output["file_tree"]
    assert "GAME_BRIEF.md" in result.output["file_tree"]
    assert "scripted the core loop" in result.output["notes_log"]
    assert result.output["scene"]["exists"] is True
    assert result.output["scene"]["node_count"] == 1
    assert result.output["scene"]["has_script"] is True
    assert result.output["has_asset_licenses"] is False


@pytest.mark.asyncio
async def test_scan_reports_xp_and_recent_events(tmp_path):
    slug, workspace = _scaffold(tmp_path)
    game_dev_xp.award(slug, "task_completed", "scaffolded project", tmp_path)
    game_dev_xp.award(slug, "task_completed", "scripted core loop", tmp_path)

    tool = ScanGameProjectTool(data_dir=tmp_path)
    with patch.object(_mod, "game_workspace_dir", return_value=workspace):
        result = await tool.execute(tool.Args(project_slug=slug), trace_id="t1")

    assert result.ok
    assert result.output["xp_total"] == 20
    assert result.output["level"] == 1
    assert len(result.output["recent_xp_events"]) == 2
    assert result.output["recent_xp_events"][0]["note"] == "scripted core loop"  # most recent first


@pytest.mark.asyncio
async def test_scan_handles_missing_optional_files_gracefully(tmp_path):
    from sovereign_agent.game_projects import GameProject, save
    save(GameProject(project_name="Bare Project", dimension="2d"), tmp_path)
    bare_workspace = tmp_path / "sandbox" / "games" / "bare-project"
    tool = ScanGameProjectTool(data_dir=tmp_path)
    with patch.object(_mod, "game_workspace_dir", return_value=bare_workspace):
        result = await tool.execute(tool.Args(project_slug="bare-project"), trace_id="t1")

    assert result.ok, result.error
    assert result.output["file_tree"] == []
    assert result.output["notes_log"] == ""
    assert result.output["scene"] == {"exists": False}
    assert result.output["xp_total"] == 0
