"""scaffold_godot_project — Tier 1. Write a REAL, minimal Godot project
(project.godot + a starter scene) into a registered game project's
workspace, so godot_check/godot_export/godot_open have something real to
operate on.

Kevin (2026-08-02): "extend her list of tools... prepare her for game
design inside of Godot... start with 2D or 2.5D and then work our way to
3D." A real gap: define_game_project() only creates a data record
(name/genre/concept), and scaffold_game_docs.py only writes markdown —
nothing actually creates the project.godot + scene the existing
godot_check/godot_export/godot_open tools need to have anything to do.
This is that missing step.

The starter scene's root node type is picked from the project's own
`dimension` field (game_projects.py): Node2D for "2d"/"2.5d" (Godot's
own convention — 2.5D is 2D gameplay with depth/perspective tricks on
the same 2D node tree, not a different engine mode), Node3D for "3d".

Never overwrites an existing project.godot — scaffolding twice on a
project that already has real work in it would be destructive; the tool
reports "already scaffolded" instead.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult

_ROOT_NODE_TYPE = {"2d": "Node2D", "2.5d": "Node2D", "3d": "Node3D"}


def _project_godot(project_name: str) -> str:
    return f'''; Engine configuration file.
; It's best edited using the editor UI and not directly, since the
; parameters that go here are not all obvious.
;
; Format:
;   [section] ; section goes between []
;   param=value ; assign values to parameters

config_version=5

[application]

config/name="{project_name}"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.3", "Forward Plus")
'''


def _main_scene(root_type: str) -> str:
    return f'''[gd_scene load_steps=1 format=3]

[node name="Main" type="{root_type}"]
'''


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project")


class ScaffoldGodotProjectTool(Tool[_Args]):
    name = "scaffold_godot_project"
    tier = 1
    description = (
        "Write a real, minimal Godot project (project.godot + a starter "
        "main.tscn) into a registered game project's workspace — the "
        "missing step between defining a concept and being able to "
        "godot_check/godot_export/godot_open it. The starter scene's root "
        "node (Node2D or Node3D) is picked from the project's own "
        "dimension field (2d/2.5d -> Node2D, 3d -> Node3D). Never "
        "overwrites an existing project.godot. "
        "FAILURE MODES: unknown_project; already_scaffolded; "
        "path_scope_violation."
    )
    failure_modes = ("unknown_project", "already_scaffolded", "path_scope_violation")
    Args = _Args

    def __init__(self, mode: Mode | None = None, data_dir: Path | None = None) -> None:
        self._mode = mode or Mode.ONESHOT
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        project = load_by_slug(args.project_slug, data_dir)
        if project is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        workspace = game_workspace_dir(args.project_slug, sandbox_dir=None)
        try:
            workspace = check_write_path(workspace, self._mode)
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=f"path_scope_violation: {e}")

        project_godot_path = workspace / "project.godot"
        if project_godot_path.exists():
            return ToolResult(
                ok=False,
                error=f"already_scaffolded: {project_godot_path} already exists",
            )

        root_type = _ROOT_NODE_TYPE.get(project.dimension, "Node2D")
        scene_path = workspace / "main.tscn"
        project_godot_path.write_text(_project_godot(project.project_name), encoding="utf-8")
        scene_path.write_text(_main_scene(root_type), encoding="utf-8")

        return ToolResult(ok=True, output={
            "project_godot_path": str(project_godot_path),
            "main_scene_path": str(scene_path),
            "dimension": project.dimension,
            "root_node_type": root_type,
            "message": f"Scaffolded a real {project.dimension} Godot project "
                      f"for {project.project_name!r} — godot_check it next.",
        })


__all__ = ["ScaffoldGodotProjectTool"]
