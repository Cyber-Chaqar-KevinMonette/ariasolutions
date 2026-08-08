"""generate_storyboard_image — Tier 1. Generate a real storyboard/key-art
still for a movie project, scoped to its own workspace.

movie-studio-d (Kevin, 2026-07-28): a thin wrapper, not new GPU code —
composes the existing, proven GenerateImageTool (local diffusion,
vram_lock-serialized, already tested) rather than reaching into its
private internals. The only new logic here is: confirm the project is
real, run the real generation, copy the real output into
movie_workspace_dir(slug)/storyboards/, and record it in the project's
asset manifest. The shared images/generated/ archive GenerateImageTool
writes to is left untouched (copy, not move) — one file, two honest
references: the general archive, and this project's own workspace.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .. import movie_assets
from ..movie_projects import load_by_slug, movie_workspace_dir
from .base import Tool, ToolResult
from .image_generate import GenerateImageTool


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered movie project")
    prompt: str = Field(description="The shot/scene to draw — as specific as a real "
                                    "storyboard panel description")
    negative_prompt: str = Field(
        default="blurry, low quality, watermark, text, signature, ugly, deformed",
        description="What to avoid in the image.",
    )
    model: str = Field(
        default="sdxl-turbo",
        description="flux-schnell (best, 6GB), sdxl-turbo (fast, 5.5GB), "
                    "sd21 (reliable, 3.5GB).",
    )
    width: int = Field(default=512, ge=256, le=1024)
    height: int = Field(default=512, ge=256, le=1024)
    steps: int = Field(default=4, ge=1, le=50)
    seed: Optional[int] = Field(default=None)


class GenerateStoryboardImageTool(Tool[_Args]):
    name = "generate_storyboard_image"
    tier = 1
    description = (
        "Generate a real storyboard/key-art still for a registered movie "
        "project — the same local diffusion pipeline generate_image uses, "
        "scoped to the project's own workspace and recorded in its asset "
        "manifest. Args: project_slug (required), prompt (required), "
        "model (flux-schnell/sdxl-turbo/sd21), width/height (256-1024), "
        "steps (1-50). "
        "FAILURE MODES: unknown_project; generation_failed."
    )
    failure_modes = ("unknown_project", "generation_failed")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        project = load_by_slug(args.project_slug, data_dir)
        if project is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        gen = GenerateImageTool()
        gen_args = gen.Args(
            prompt=args.prompt, negative_prompt=args.negative_prompt,
            model=args.model, width=args.width, height=args.height,
            steps=args.steps, seed=args.seed,
        )
        result = await gen.execute(gen_args, trace_id=trace_id)
        if not result.ok:
            return ToolResult(ok=False, error=f"generation_failed: {result.error}")

        workspace = movie_workspace_dir(args.project_slug, sandbox_dir=None)
        storyboards_dir = workspace / "storyboards"
        storyboards_dir.mkdir(parents=True, exist_ok=True)
        src = Path(result.output)
        dest = storyboards_dir / src.name
        dest.write_bytes(src.read_bytes())

        rel = f"storyboards/{dest.name}"
        movie_assets.record_asset(
            workspace, relative_path=rel,
            kind="storyboard", source_tool="generate_storyboard_image")

        return ToolResult(ok=True, output={
            "path": str(dest),
            "archive_path": str(src),
            "message": f"Generated a storyboard still for {project.title!r} → {rel}",
        })


__all__ = ["GenerateStoryboardImageTool"]
