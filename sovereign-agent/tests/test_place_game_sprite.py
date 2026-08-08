"""Tests for place_game_sprite — generate, import, and place a sprite into
a real Godot scene. Generation itself is mocked (GenerateImageTool is
exercised for real elsewhere, e.g. test_image_generate.py / the
create.image capability test) so these stay fast and GPU-free."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sovereign_agent.game_projects import GameProject, game_workspace_dir, save
from sovereign_agent.sprite_qa import SpriteQAResult
from sovereign_agent.tools.base import ToolResult
from sovereign_agent.tools.place_game_sprite import PlaceGameSpriteTool, _place_in_scene

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc\xf8\xcf\xc0\x00"
    b"\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _fake_generate_tool_ok(tmp_path):
    src = tmp_path / "generated_source.png"
    src.write_bytes(_TINY_PNG)

    class _FakeGenerateImageTool:
        Args = _FakeArgs

        async def execute(self, _args, *, trace_id):  # noqa: ARG002
            return ToolResult(ok=True, output=str(src), metadata={})

    return _FakeGenerateImageTool


def _qa_passthrough(mod):
    """The real rembg/QA pipeline is exercised for real elsewhere (a live
    generation test); here it's mocked as a no-op pass-through — same
    "generation is mocked, keep these fast/GPU-free" philosophy this file
    already states, extended to the QA step."""
    return (
        patch.object(mod, "remove_background", side_effect=lambda b: b),
        patch.object(mod, "check_sprite_quality",
                     side_effect=lambda b, **kw: SpriteQAResult(ok=True, warnings=[], png_bytes=b)),
    )


def _fake_generate_tool_fail(error: str):
    class _FakeGenerateImageTool:
        Args = _FakeArgs

        async def execute(self, _args, *, trace_id):  # noqa: ARG002
            return ToolResult(ok=False, error=error)

    return _FakeGenerateImageTool


def _scaffold(tmp_path, project_name="Flat Runner", dimension="2d"):
    save(GameProject(project_name=project_name, dimension=dimension), tmp_path)
    slug = project_name.lower().replace(" ", "-")
    sandbox = tmp_path / "sandbox"
    workspace = game_workspace_dir(slug, sandbox_dir=sandbox)
    root_type = "Node3D" if dimension == "3d" else "Node2D"
    (workspace / "project.godot").write_text(f'config/name="{project_name}"\n')
    (workspace / "main.tscn").write_text(
        f'[gd_scene load_steps=1 format=3]\n\n[node name="Main" type="{root_type}"]\n'
    )
    return slug, workspace


# ── _place_in_scene header-format handling ──────────────────────────────

def test_place_in_scene_handles_our_own_scaffolded_header():
    scene = '[gd_scene load_steps=1 format=3]\n\n[node name="Main" type="Node2D"]\n'
    result, name = _place_in_scene(
        scene, node_type="Sprite2D", node_name="Ember", res_path="res://assets/sprites/ember.png"
    )
    assert "[gd_scene load_steps=2 format=3]" in result
    assert name == "Ember"


def test_place_in_scene_handles_godots_own_resaved_header():
    """Regression test for the real bug found live 2026-08-02: the moment
    a human opens+saves a scene in the actual Godot editor, it gets
    rewritten to Godot's own canonical form — no load_steps at all when
    it isn't needed, plus a uid= attribute. This is the EXACT header
    string observed on Ember Keep's main.tscn after Kevin opened it."""
    scene = ('[gd_scene format=3 uid="uid://wsp7en0t72o7"]\n\n'
             '[ext_resource type="Script" uid="uid://c6vb1mydeillx" path="res://fire.gd" id="1"]\n\n'
             '[node name="Main" type="Node2D" unique_id=2142514900]\n'
             'script = ExtResource("1")\n')
    result, name = _place_in_scene(
        scene, node_type="Sprite2D", node_name="EmberCore",
        res_path="res://assets/sprites/ember_core.png",
    )
    assert '[gd_scene load_steps=2 format=3 uid="uid://wsp7en0t72o7"]' in result
    # the uid attribute must survive untouched — it's Godot's own stable
    # identity for the resource, not something this tool should ever alter
    assert 'uid="uid://wsp7en0t72o7"' in result
    assert name == "EmberCore"


def test_place_in_scene_rejects_missing_format_attribute():
    scene = '[gd_scene load_steps=1]\n\n[node name="Main" type="Node2D"]\n'
    with pytest.raises(ValueError, match="format"):
        _place_in_scene(scene, node_type="Sprite2D", node_name="Ember", res_path="res://x.png")


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", prompt="a knight", sprite_name="Knight"),
        trace_id="t1",
    )
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_not_scaffolded_refused(tmp_path):
    save(GameProject(project_name="No Scaffold Yet", dimension="2d"), tmp_path)
    sandbox = tmp_path / "sandbox"
    workspace = game_workspace_dir("no-scaffold-yet", sandbox_dir=sandbox)
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p):
        result = await tool.execute(
            tool.Args(project_slug="no-scaffold-yet", prompt="a knight", sprite_name="Knight"),
            trace_id="t1",
        )
    assert not result.ok
    assert "project_not_scaffolded" in result.error


@pytest.mark.asyncio
async def test_generation_failure_propagates(tmp_path):
    slug, workspace = _scaffold(tmp_path)
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p), \
         patch.object(mod, "GenerateImageTool", _fake_generate_tool_fail("insufficient VRAM")):
        result = await tool.execute(
            tool.Args(project_slug=slug, prompt="a knight", sprite_name="Knight"),
            trace_id="t1",
        )
    assert not result.ok
    assert "generation_failed" in result.error
    assert "insufficient VRAM" in result.error


@pytest.mark.asyncio
async def test_quality_check_failure_blocks_placement(tmp_path):
    """A degenerate/failed generation must never reach the scene file —
    the real bug this closes: place_game_sprite's first live run wired a
    broken multi-panel, non-transparent image straight into main.tscn
    with zero warning."""
    slug, workspace = _scaffold(tmp_path)
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p), \
         patch.object(mod, "GenerateImageTool", _fake_generate_tool_ok(tmp_path)), \
         patch.object(mod, "remove_background", side_effect=lambda b: b), \
         patch.object(mod, "check_sprite_quality",
                       return_value=SpriteQAResult(ok=False, warnings=["degenerate image"])):
        result = await tool.execute(
            tool.Args(project_slug=slug, prompt="a knight", sprite_name="Knight"),
            trace_id="t1",
        )
    assert not result.ok
    assert "generation_failed" in result.error
    assert "degenerate image" in result.error
    assert not (workspace / "assets" / "sprites" / "knight.png").exists()
    scene = (workspace / "main.tscn").read_text()
    assert "Knight" not in scene


@pytest.mark.asyncio
async def test_background_removal_exception_is_reported(tmp_path):
    slug, workspace = _scaffold(tmp_path)
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod

    def _boom(_b):
        raise RuntimeError("onnxruntime session failed")

    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p), \
         patch.object(mod, "GenerateImageTool", _fake_generate_tool_ok(tmp_path)), \
         patch.object(mod, "remove_background", side_effect=_boom):
        result = await tool.execute(
            tool.Args(project_slug=slug, prompt="a knight", sprite_name="Knight"),
            trace_id="t1",
        )
    assert not result.ok
    assert "generation_failed" in result.error
    assert "onnxruntime session failed" in result.error


@pytest.mark.asyncio
async def test_negative_prompt_default_steers_away_from_collages():
    tool = PlaceGameSpriteTool()
    args = tool.Args(project_slug="x", prompt="a knight", sprite_name="Knight")
    assert "collage" in args.negative_prompt
    assert "grid" in args.negative_prompt
    assert "sprite sheet" in args.negative_prompt


@pytest.mark.asyncio
async def test_2d_project_places_sprite2d(tmp_path):
    slug, workspace = _scaffold(tmp_path, project_name="Flat Runner", dimension="2d")
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod
    qa_bg, qa_check = _qa_passthrough(mod)
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p), \
         patch.object(mod, "GenerateImageTool", _fake_generate_tool_ok(tmp_path)), \
         qa_bg, qa_check:
        result = await tool.execute(
            tool.Args(project_slug=slug, prompt="a knight", sprite_name="Knight"),
            trace_id="t1",
        )
    assert result.ok, result.error
    assert result.output["node_type"] == "Sprite2D"
    assert result.output["background_removed"] is True
    sprite_path = workspace / "assets" / "sprites" / "knight.png"
    assert sprite_path.is_file()
    assert sprite_path.read_bytes() == _TINY_PNG
    scene = (workspace / "main.tscn").read_text()
    assert 'ext_resource type="Texture2D" path="res://assets/sprites/knight.png"' in scene
    assert '[node name="Knight" type="Sprite2D" parent="."]' in scene
    assert 'texture = ExtResource(' in scene
    assert "load_steps=2" in scene


@pytest.mark.asyncio
async def test_3d_project_places_sprite3d(tmp_path):
    slug, workspace = _scaffold(tmp_path, project_name="Cube World", dimension="3d")
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod
    qa_bg, qa_check = _qa_passthrough(mod)
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p), \
         patch.object(mod, "GenerateImageTool", _fake_generate_tool_ok(tmp_path)), \
         qa_bg, qa_check:
        result = await tool.execute(
            tool.Args(project_slug=slug, prompt="a coin", sprite_name="Coin"),
            trace_id="t1",
        )
    assert result.ok, result.error
    assert result.output["node_type"] == "Sprite3D"
    scene = (workspace / "main.tscn").read_text()
    assert '[node name="Coin" type="Sprite3D" parent="."]' in scene


@pytest.mark.asyncio
async def test_duplicate_node_name_is_deduped(tmp_path):
    slug, workspace = _scaffold(tmp_path, project_name="Flat Runner", dimension="2d")
    tool = PlaceGameSpriteTool(data_dir=tmp_path)
    import sovereign_agent.tools.place_game_sprite as mod
    qa_bg, qa_check = _qa_passthrough(mod)
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p), \
         patch.object(mod, "GenerateImageTool", _fake_generate_tool_ok(tmp_path)), \
         qa_bg, qa_check:
        first = await tool.execute(
            tool.Args(project_slug=slug, prompt="a knight", sprite_name="Knight"),
            trace_id="t1",
        )
        second = await tool.execute(
            tool.Args(project_slug=slug, prompt="a second knight", sprite_name="Knight"),
            trace_id="t2",
        )
    assert first.ok and second.ok
    assert first.output["node_name"] == "Knight"
    assert second.output["node_name"] == "Knight2"
    scene = (workspace / "main.tscn").read_text()
    assert scene.count('[node name="Knight"') == 1
    assert scene.count('[node name="Knight2"') == 1
