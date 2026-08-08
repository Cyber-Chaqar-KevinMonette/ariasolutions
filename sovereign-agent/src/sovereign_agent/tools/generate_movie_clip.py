"""generate_movie_clip — Tier 1. Generate a real video clip for a movie
project, scoped to its own workspace.

movie-studio-d Phase 2 (Kevin, 2026-07-28): local, FOSS-only video
generation — LTX-Video via diffusers, the same library image_generate.py
already uses. No cloud, no external dependency, no per-clip cost, real
speed cost accepted on purpose ("we will take local over speed").

Confirmed live on this exact GTX 1070 (8GB, Pascal) after real testing:
  - The plain `Lightricks/LTX-Video` checkpoint (~10GB documented) does
    NOT fit with enable_model_cpu_offload() alone — that's the technique
    that safely fixed image_generate.py's real SDXL OOM bug, but here it
    still OOM'd loading the text encoder (7.6GB already committed to the
    transformer). enable_sequential_cpu_offload() (layer-by-layer, not
    component-by-component) is slower but confirmed safe across four
    repeated real runs.
  - NEVER use the official docs' fp8-layerwise-casting + CUDA-stream
    group-offloading recipe on this machine — that combination froze the
    whole PC solid and needed a hard reboot to recover. Sequential
    offload alone is the proven-safe path here.
  - This is the BASE (non-distilled) checkpoint, so it needs a real step
    count and real guidance — confirmed 8 steps produces washed-out,
    barely-visible output; 30 steps + guidance_scale=5.0 produces a real,
    recognizable result. Don't drop these to "make it faster" without
    re-testing quality.
  - num_frames should follow LTX's VAE temporal compression pattern
    (8k+1 — 9, 17, 25, ...); 9 is the confirmed-working minimum.

VRAM strategy: vram_lock() serializes with qwen3:8b, same as
image_generate.py. GPU work runs in a thread executor so the event loop
stays responsive. Real generation is slow (~1-3 min for a tiny clip on
this hardware) — that's the accepted, deliberate tradeoff, not a bug.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, Field

from ..movie_assets import record_asset
from ..movie_projects import load_by_slug, movie_workspace_dir
from ..vram import vram_lock
from .base import Tool, ToolResult
from .image_generate import _slug

_HF_REPO = "Lightricks/LTX-Video"

OnStep = Optional[Callable[[int, int], None]]


def _make_step_callback(on_step: OnStep, total_steps: int):
    """Wraps a plain (step, total_steps) callback into diffusers' real
    `callback_on_step_end(pipe, step_index, timestep, callback_kwargs)`
    convention (confirmed live in diffusers/pipelines/ltx/pipeline_ltx.py
    — genuine per-denoising-step progress, not a fake timer). Must return
    the (possibly-empty) callback_kwargs dict diffusers expects back."""
    if on_step is None:
        return None

    def _cb(pipe, step_index, timestep, callback_kwargs):  # noqa: ANN001, ARG001
        try:
            on_step(step_index + 1, total_steps)
        except Exception:  # noqa: BLE001 — a broken UI callback must never break generation
            pass
        return callback_kwargs

    return _cb


def _sync_generate_ltx(
    prompt: str, negative_prompt: str, width: int, height: int,
    num_frames: int, steps: int, guidance_scale: float,
    seed: Optional[int], out_path: Path, *, on_step: OnStep = None,
) -> None:
    import torch
    from diffusers import LTXPipeline
    from diffusers.utils import export_to_video

    pipe = LTXPipeline.from_pretrained(_HF_REPO, torch_dtype=torch.bfloat16)
    pipe.enable_sequential_cpu_offload()
    try:
        pipe.vae.enable_tiling()
    except Exception:  # noqa: BLE001
        pass

    gen = torch.Generator().manual_seed(seed) if seed is not None else None
    call_kwargs = dict(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        decode_timestep=0.05,
        decode_noise_scale=0.025,
        generator=gen,
    )
    cb = _make_step_callback(on_step, steps)
    if cb is not None:
        call_kwargs["callback_on_step_end"] = cb
    video = pipe(**call_kwargs).frames[0]

    export_to_video(video, str(out_path), fps=8)


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered movie project")
    prompt: str = Field(description="The shot/scene to animate")
    negative_prompt: str = Field(
        default="worst quality, inconsistent motion, blurry, jittery, distorted",
        description="What to avoid in the clip.",
    )
    width: int = Field(default=256, ge=256, le=512)
    height: int = Field(default=256, ge=256, le=512)
    num_frames: int = Field(
        default=9, ge=9, le=49,
        description="Real frame count — follow the 8k+1 pattern (9, 17, 25, "
                    "...). 9 is the confirmed-working minimum on this hardware.",
    )
    steps: int = Field(
        default=30, ge=8, le=50,
        description="30 is confirmed to produce recognizable output on this "
                    "base (non-distilled) checkpoint; 8 was tested and is "
                    "too washed-out to use for real.",
    )
    guidance_scale: float = Field(default=5.0, ge=1.0, le=10.0)
    seed: Optional[int] = Field(default=None)


class GenerateMovieClipTool(Tool[_Args]):
    name = "generate_movie_clip"
    tier = 1
    description = (
        "Generate a real video clip for a registered movie project via "
        "local LTX-Video (FOSS, diffusers-based, no cloud, no cost) — "
        "confirmed working on this exact GPU. Scoped to the project's own "
        "workspace, recorded in its asset manifest. Slow (~1-3 min for a "
        "tiny clip) and low-resolution by design — local-over-speed, a "
        "deliberate tradeoff, not a bug. "
        "FAILURE MODES: unknown_project; generation_failed; insufficient_vram."
    )
    failure_modes = ("unknown_project", "generation_failed", "insufficient_vram")
    Args = _Args

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str, on_step: OnStep = None) -> ToolResult:  # noqa: ARG002
        """on_step is a Python-callers-only extension (not part of the
        pydantic Args schema an LLM tool-call would fill in) — real
        per-denoising-step progress, wired up by
        cockpit/movie_generation_actions.py for the movie pane's "watch it
        generate live" status. Optional everywhere else; the LLM/authority
        tool-calling path never passes it and behaves exactly as before."""
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        project = load_by_slug(args.project_slug, data_dir)
        if project is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        workspace = movie_workspace_dir(args.project_slug, sandbox_dir=None)
        clips_dir = workspace / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        out_path = clips_dir / f"{ts}_{_slug(args.prompt)}.mp4"

        loop = asyncio.get_event_loop()
        try:
            with vram_lock("generate_movie_clip"):
                await loop.run_in_executor(
                    None,
                    lambda: _sync_generate_ltx(
                        args.prompt, args.negative_prompt, args.width, args.height,
                        args.num_frames, args.steps, args.guidance_scale, args.seed,
                        out_path, on_step=on_step,
                    ),
                )
        except ImportError as exc:
            return ToolResult(
                ok=False,
                error=f"missing dependency: {exc}. Run: pip install diffusers "
                     "sentencepiece protobuf imageio imageio-ffmpeg")
        except Exception as exc:  # noqa: BLE001
            s = str(exc)
            if "CUDA" in s and "memory" in s.lower():
                return ToolResult(ok=False, error=f"insufficient_vram: {s[:300]}")
            return ToolResult(
                ok=False, error=f"generation_failed: {type(exc).__name__}: {s[:300]}")

        rel = f"clips/{out_path.name}"
        record_asset(workspace, relative_path=rel, kind="clip",
                    source_tool="generate_movie_clip")

        return ToolResult(ok=True, output={
            "path": str(out_path),
            "message": f"Generated a real video clip for {project.title!r} → {rel}",
        })


__all__ = ["GenerateMovieClipTool"]
