"""place_game_sprite — Tier 1. Generate a sprite, import it into a game
project's assets, and place it in the project's scene — one wired call.

Kevin (2026-08-02): "generate, import, and place it where it belongs."
Real gap: create.game_art (image_generate.py's GenerateImageTool) writes a
PNG to data_dir/images/generated/ and stops there — nothing connected that
art to an actual Godot project. This tool closes that gap by reusing
GenerateImageTool for the real GPU work (no diffusion code duplicated),
then doing the two missing steps: copy the PNG into the project's own
workspace/assets/sprites/, and add a real ext_resource + Sprite2D/Sprite3D
node for it into main.tscn (sprite type follows the same dimension
routing scaffold_godot_project.py already uses).

Per Kevin's "0% of it — I want it all to be her": this is a tool Aria
calls herself with a prompt and placement she decides (informed by
game_design_brief's art-direction section), not a GamePane button Kevin
operates by hand — no UI wiring here, on purpose.

Requires the project to already be scaffolded (main.tscn must exist) —
same dependency godot_check/godot_export/godot_open already have on
scaffold_godot_project.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..game_projects import game_workspace_dir, load_by_slug
from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from ..resilience import guarded_execute
from ..sprite_qa import ANTI_COLLAGE_TERMS, check_sprite_quality, remove_background
from .base import Tool, ToolResult
from .image_generate import GenerateImageTool

_SPRITE_NODE_TYPE = {"2d": "Sprite2D", "2.5d": "Sprite2D", "3d": "Sprite3D"}

# Matches the [gd_scene ...] header generically — found live 2026-08-02:
# the strict "[gd_scene load_steps=N format=F]" form only matches scenes
# we scaffolded ourselves. The instant a human opens+saves the scene in
# the real Godot editor, it gets rewritten to Godot's OWN canonical form,
# which drops load_steps entirely when it isn't needed and adds a
# uid="..." attribute — e.g. "[gd_scene format=3 uid=\"uid://...\"]". The
# strict regex simply didn't match that at all, breaking sprite placement
# on any project a human had so much as looked at once.
_GD_SCENE_HEADER_RE = re.compile(r"\[gd_scene\b([^\]]*)\]")
_LOAD_STEPS_ATTR_RE = re.compile(r"\bload_steps=(\d+)\b")
_FORMAT_ATTR_RE = re.compile(r"\bformat=(\d+)\b")
_EXT_RESOURCE_ID_RE = re.compile(r'\[ext_resource\b[^\]]*\bid="(\d+)"')
_NODE_NAME_RE = re.compile(r'\[node name="([^"]+)"')


def _file_slug(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "_", s).strip("_")
    return s[:maxlen] or "sprite"


def _node_name(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", " ", text).title().replace(" ", "")
    return s[:maxlen] or "Sprite"


def _place_in_scene(scene_text: str, *, node_type: str, node_name: str, res_path: str) -> str:
    header = _GD_SCENE_HEADER_RE.search(scene_text)
    if header is None:
        raise ValueError("no [gd_scene ...] header found")
    attrs = header.group(1)
    if _FORMAT_ATTR_RE.search(attrs) is None:
        raise ValueError("gd_scene header missing format=")

    existing_steps_match = _LOAD_STEPS_ATTR_RE.search(attrs)
    existing_steps = int(existing_steps_match.group(1)) if existing_steps_match else 1
    new_steps = existing_steps + 1
    if existing_steps_match:
        # Preserve every other attribute (uid=, etc.) untouched — only
        # load_steps changes.
        new_attrs = _LOAD_STEPS_ATTR_RE.sub(f"load_steps={new_steps}", attrs, count=1)
    else:
        new_attrs = f" load_steps={new_steps}" + attrs

    text = (scene_text[:header.start()] + f"[gd_scene{new_attrs}]"
            + scene_text[header.end():])

    existing_ids = [int(m) for m in _EXT_RESOURCE_ID_RE.findall(text)]
    next_id = max(existing_ids, default=0) + 1

    existing_names = set(_NODE_NAME_RE.findall(text))
    name = node_name
    suffix = 2
    while name in existing_names:
        name = f"{node_name}{suffix}"
        suffix += 1

    ext_resource_line = f'[ext_resource type="Texture2D" path="{res_path}" id="{next_id}"]'
    node_idx = text.index("[node")
    text = text[:node_idx] + ext_resource_line + "\n\n" + text[node_idx:]

    node_block = (
        f'\n[node name="{name}" type="{node_type}" parent="."]\n'
        f'texture = ExtResource("{next_id}")\n'
    )
    text = text.rstrip("\n") + "\n" + node_block
    return text, name


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered, already-scaffolded game project")
    prompt: str = Field(description="Text description of the sprite to generate.")
    sprite_name: str = Field(description="Name for the sprite — used as both the scene node name and the saved filename.")
    negative_prompt: str = Field(
        default=f"blurry, low quality, watermark, text, signature, ugly, "
                f"deformed, {ANTI_COLLAGE_TERMS}",
        description="What to avoid in the image. The default already steers "
                    "away from multi-panel/collage output (a real failure "
                    "mode observed live) — extend it, don't replace it "
                    "wholesale, unless you have a specific reason to.",
    )
    model: str = Field(default="sdxl-turbo", description="sdxl-turbo (works here, no auth), flux-schnell (best, needs HF auth), sd21 (reliable).")
    width: int = Field(default=512, ge=256, le=1024)
    height: int = Field(default=512, ge=256, le=1024)
    steps: int = Field(default=4, ge=1, le=50)
    seed: Optional[int] = Field(default=None)


class PlaceGameSpriteTool(Tool[_Args]):
    name = "place_game_sprite"
    tier = 1
    description = (
        "Generate a 2D sprite from a text prompt, import it into a "
        "registered game project's assets/sprites/, and place it as a "
        "Sprite2D (or Sprite3D for a 3D project) node in the project's "
        "main.tscn — one wired call from prompt to a real, referenced "
        "in-scene sprite. Requires the project to already be scaffolded "
        "(scaffold_godot_project first). "
        "FAILURE MODES: unknown_project; project_not_scaffolded; "
        "generation_failed; path_scope_violation; scene_write_failed."
    )
    failure_modes = (
        "unknown_project",
        "project_not_scaffolded",
        "generation_failed",
        "path_scope_violation",
        "scene_write_failed",
    )
    Args = _Args

    def __init__(self, mode: Mode | None = None, data_dir: Path | None = None) -> None:
        self._mode = mode or Mode.ONESHOT
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:
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

        scene_path = workspace / "main.tscn"
        if not scene_path.exists():
            return ToolResult(
                ok=False,
                error=f"project_not_scaffolded: {scene_path} does not exist — "
                      "run scaffold_godot_project first",
            )

        gen_tool = GenerateImageTool()
        gen_result = await guarded_execute(
            gen_tool,
            gen_tool.Args(
                prompt=args.prompt,
                negative_prompt=args.negative_prompt,
                model=args.model,
                width=args.width,
                height=args.height,
                steps=args.steps,
                seed=args.seed,
            ),
            trace_id=f"{trace_id}-generate",
            breaker_name="tool:generate_image",
        )
        if not gen_result.ok:
            return ToolResult(ok=False, error=f"generation_failed: {gen_result.error}")

        # sprite-qa-d (2026-08-02): a plain prompt cannot produce real alpha
        # — matte the subject out for real, then sanity-check the result
        # before it's ever wired into the scene as a texture.
        raw_bytes = Path(gen_result.output).read_bytes()
        try:
            matted_bytes = remove_background(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"generation_failed: background removal failed: {exc!r}")

        qa = check_sprite_quality(matted_bytes, expected_width=args.width, expected_height=args.height)
        if not qa.ok:
            return ToolResult(
                ok=False,
                error=f"generation_failed: quality check failed — {'; '.join(qa.warnings)}",
            )
        png_bytes = qa.png_bytes

        file_stem = _file_slug(args.sprite_name or args.prompt)
        target = workspace / "assets" / "sprites" / f"{file_stem}.png"
        try:
            target = check_write_path(target, self._mode)
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=f"path_scope_violation: {e}")

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(png_bytes)
        tmp.replace(target)

        node_type = _SPRITE_NODE_TYPE.get(project.dimension, "Sprite2D")
        try:
            new_scene_text, placed_name = _place_in_scene(
                scene_path.read_text(encoding="utf-8"),
                node_type=node_type,
                node_name=_node_name(args.sprite_name),
                res_path=f"res://assets/sprites/{file_stem}.png",
            )
        except ValueError as e:
            return ToolResult(ok=False, error=f"scene_write_failed: {e}")

        scene_tmp = scene_path.with_suffix(scene_path.suffix + ".tmp")
        scene_tmp.write_text(new_scene_text, encoding="utf-8")
        scene_tmp.replace(scene_path)

        return ToolResult(ok=True, output={
            "sprite_path": str(target),
            "scene_path": str(scene_path),
            "node_name": placed_name,
            "node_type": node_type,
            "generated_from": gen_result.output,
            "background_removed": True,
            "qa_warnings": qa.warnings,
            "message": f"Generated {placed_name!r}, background-removed, "
                      f"imported to assets/sprites/{file_stem}.png, and "
                      f"placed as {node_type} {placed_name!r} in "
                      "main.tscn — godot_check it next."
                      + (f" QA warnings: {'; '.join(qa.warnings)}" if qa.warnings else ""),
        })


__all__ = ["PlaceGameSpriteTool"]
