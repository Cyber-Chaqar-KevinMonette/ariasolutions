"""
image_edit.py — image editing (img2img, inpainting, variation) for Aria

Two Tier 1 tools that transform existing images using local diffusion models:

  edit_image     — img2img: transform an image with a new text prompt.
                   Change style, lighting, content, season, mood.
                   Uses SDXL-Turbo (fastest img2img) or SD2.1.

  inpaint_image  — inpainting: fill a masked region with generated content.
                   Requires a mask image (white = area to repaint).
                   Uses SD2-inpainting model.

Both use vram_lock to serialize with qwen3:8b, run in thread executor
to keep the event loop responsive, and save results to
data_dir/images/edited/.

Strength parameter controls how much to change the image:
  0.1-0.3 = subtle variations (lighting, color grading, minor details)
  0.4-0.6 = moderate transformation (style, mood, composition)
  0.7-0.9 = heavy transformation (genre, season, major visual change)
  1.0     = fully ignore original (equivalent to txt2img)
"""
from __future__ import annotations

import asyncio
import io
import os
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from sovereign_agent.config import SETTINGS
from sovereign_agent.vram import SAFETY_FLOOR_MB, vram_lock

from .base import Tool, ToolResult


_HF_SDXL_TURBO = "stabilityai/sdxl-turbo"
_HF_SD21 = "stabilityai/stable-diffusion-2-1"
_HF_SD21_INPAINT = "stabilityai/stable-diffusion-2-inpainting"
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB per image


def _load_pil(path: str):
    """Load image as PIL.Image in RGB mode."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError(f"path must be absolute: {path!r}")
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")
    if p.stat().st_size > _MAX_BYTES:
        raise ValueError(f"file too large: {p.stat().st_size} bytes")
    from PIL import Image
    return Image.open(p).convert("RGB")


def _to_png_bytes(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _slug(path: str, suffix: str = "edited") -> str:
    stem = Path(path).stem[:30]
    return f"{stem}_{suffix}"


# ── synchronous generation (thread executor) ──────────────────────────────────


def _sync_edit_sdxl_turbo(
    image,
    prompt: str,
    negative_prompt: str,
    strength: float,
    steps: int,
    seed: Optional[int],
):
    import torch
    from diffusers import AutoPipelineForImage2Image

    pipe = AutoPipelineForImage2Image.from_pretrained(
        _HF_SDXL_TURBO,
        torch_dtype=torch.float16,
        variant="fp16",
    ).to("cuda")

    gen = torch.Generator(device="cuda").manual_seed(seed) if seed is not None else None
    result = pipe(
        prompt=prompt,
        image=image,
        num_inference_steps=min(steps, 4),
        strength=strength,
        guidance_scale=0.0,
        generator=gen,
    ).images[0]
    return _to_png_bytes(result)


def _sync_edit_sd21(
    image,
    prompt: str,
    negative_prompt: str,
    strength: float,
    steps: int,
    seed: Optional[int],
):
    import torch
    from diffusers import StableDiffusionImg2ImgPipeline

    pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
        _HF_SD21,
        torch_dtype=torch.float16,
    ).to("cuda")

    gen = torch.Generator(device="cuda").manual_seed(seed) if seed is not None else None
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=image,
        strength=strength,
        num_inference_steps=steps,
        generator=gen,
    ).images[0]
    return _to_png_bytes(result)


def _sync_inpaint(
    image,
    mask,
    prompt: str,
    negative_prompt: str,
    steps: int,
    seed: Optional[int],
):
    import torch
    from diffusers import StableDiffusionInpaintPipeline

    pipe = StableDiffusionInpaintPipeline.from_pretrained(
        _HF_SD21_INPAINT,
        torch_dtype=torch.float16,
    ).to("cuda")

    gen = torch.Generator(device="cuda").manual_seed(seed) if seed is not None else None
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=image,
        mask_image=mask,
        num_inference_steps=steps,
        generator=gen,
    ).images[0]
    return _to_png_bytes(result)


# ── EditImageTool ─────────────────────────────────────────────────────────────


class EditImageTool(Tool):
    """Transform an existing image using a text prompt (img2img).

    Preserves the structure and composition of the original while applying
    the style, mood, content, or color described in the prompt.
    The `strength` parameter controls how much to change:

      0.1 = subtle (color grade, lighting tweak)
      0.4 = moderate (style change: photo → oil painting)
      0.7 = heavy (season, genre: summer → winter, realistic → anime)
      1.0 = full regeneration (ignore original, use as loose inspiration)

    Example use cases:
      - "make this a watercolor painting" strength=0.5
      - "change to winter scene with snow" strength=0.6
      - "professional studio lighting" strength=0.3
      - "convert to pencil sketch" strength=0.7
      - "make the sky more dramatic" strength=0.4
    """

    name = "edit_image"
    tier = 1  # Tier 1: writes files to sandbox
    description = (
        "Transform an existing image with a text prompt (img2img). "
        "Args: path (required), prompt (required), model (sdxl-turbo/sd21), "
        "strength (0.1-1.0, default 0.5), negative_prompt, steps, seed. "
        "strength=0.3 = subtle, 0.6 = heavy. "
        "Saves to data_dir/images/edited/ and returns path. VRAM-serialized."
    )
    failure_modes = (
        "diffusers/torch/Pillow not installed",
        "source image not found or unreadable",
        "source image too large (>20MB)",
        "insufficient VRAM (need ~5.5GB)",
        "CUDA unavailable",
    )

    class Args(BaseModel):
        path: str = Field(description="Absolute path to the source image to edit.")
        prompt: str = Field(description="Text description of the desired result.")
        negative_prompt: str = Field(
            default="blurry, low quality, watermark, ugly, deformed",
            description="What to avoid in the output.",
        )
        model: str = Field(
            default="sdxl-turbo",
            description="Model: sdxl-turbo (fast, 4-step) or sd21 (slower, higher quality).",
        )
        strength: float = Field(
            default=0.5,
            ge=0.05,
            le=1.0,
            description="How much to change (0.1=subtle, 0.5=moderate, 0.9=heavy).",
        )
        steps: int = Field(default=4, ge=1, le=50, description="Inference steps.")
        seed: Optional[int] = Field(default=None, description="Seed for reproducibility.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        model = args.model.lower()
        if model not in ("sdxl-turbo", "sd21"):
            return ToolResult(ok=False, error=f"unknown model {model!r}. use: sdxl-turbo, sd21")

        try:
            image = _load_pil(args.path)
        except (FileNotFoundError, ValueError, OSError) as exc:
            return ToolResult(ok=False, error=str(exc))

        data_dir = SETTINGS.paths.data_dir
        if data_dir is None:
            return ToolResult(ok=False, error="data_dir not configured")

        out_dir = Path(data_dir) / "images" / "edited"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = int(time.time())
        out_path = out_dir / f"{ts}_{_slug(args.path)}.png"

        sync_fn = _sync_edit_sdxl_turbo if model == "sdxl-turbo" else _sync_edit_sd21
        loop = asyncio.get_event_loop()

        t0 = time.monotonic()
        try:
            with vram_lock("edit_image"):
                png_bytes = await loop.run_in_executor(
                    None,
                    sync_fn,
                    image,
                    args.prompt,
                    args.negative_prompt,
                    args.strength,
                    args.steps,
                    args.seed,
                )
        except ImportError as exc:
            return ToolResult(
                ok=False,
                error=f"missing dependency: {exc}. Run: pip install diffusers transformers accelerate torch Pillow",
            )
        except RuntimeError as exc:
            s = str(exc)
            if "CUDA" in s:
                return ToolResult(ok=False, error=f"CUDA error: {s[:200]}")
            return ToolResult(ok=False, error=f"edit failed: {s[:200]}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        elapsed = time.monotonic() - t0

        try:
            out_path.write_bytes(png_bytes)
        except OSError as exc:
            return ToolResult(ok=False, error=f"failed to save: {exc}")

        return ToolResult(
            ok=True,
            output=str(out_path),
            metadata={
                "path": str(out_path),
                "source": args.path,
                "model": model,
                "strength": args.strength,
                "steps": args.steps,
                "seed": args.seed,
                "elapsed_seconds": round(elapsed, 1),
                "size_bytes": len(png_bytes),
                "prompt": args.prompt[:100],
            },
        )


# ── InpaintImageTool ──────────────────────────────────────────────────────────


class InpaintImageTool(Tool):
    """Fill a region of an image with AI-generated content (inpainting).

    Requires two images: the source and a mask (white = repaint, black = keep).
    The AI fills only the white region of the mask while leaving the rest intact.

    Common use cases:
      - Remove an object (mask the object, prompt "background continuation")
      - Replace a face or element (mask it, prompt the replacement)
      - Fix a damaged or unwanted area
      - Add something new to a specific location

    Creating a mask:
      - Any image editor (GIMP, Krita) — paint white over the area to replace
      - Or generate one programmatically (pure white/black PNG at same size)
    """

    name = "inpaint_image"
    tier = 1  # Tier 1: writes files
    description = (
        "Fill a masked region of an image with AI-generated content. "
        "Args: path (source image), mask_path (white=repaint/black=keep), "
        "prompt (what to put there), negative_prompt, steps, seed. "
        "Saves to data_dir/images/edited/. Requires ~4GB VRAM (SD2-inpainting)."
    )
    failure_modes = (
        "diffusers/torch/Pillow not installed",
        "source or mask image not found",
        "mask image size doesn't match source (must be same dimensions)",
        "insufficient VRAM (need ~4GB)",
        "CUDA unavailable",
    )

    class Args(BaseModel):
        path: str = Field(description="Absolute path to the source image.")
        mask_path: str = Field(
            description="Absolute path to the mask image (white=area to repaint, black=keep).",
        )
        prompt: str = Field(description="What to generate in the masked area.")
        negative_prompt: str = Field(
            default="blurry, low quality, watermark, ugly, deformed",
            description="What to avoid in the generated area.",
        )
        steps: int = Field(default=20, ge=5, le=50, description="Inference steps.")
        seed: Optional[int] = Field(default=None, description="Seed for reproducibility.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            image = _load_pil(args.path)
            mask = _load_pil(args.mask_path)
        except (FileNotFoundError, ValueError, OSError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if image.size != mask.size:
            return ToolResult(
                ok=False,
                error=(
                    f"mask size {mask.size} doesn't match source {image.size}. "
                    "Mask must be the exact same dimensions as the source image."
                ),
            )

        data_dir = SETTINGS.paths.data_dir
        if data_dir is None:
            return ToolResult(ok=False, error="data_dir not configured")

        out_dir = Path(data_dir) / "images" / "edited"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = int(time.time())
        out_path = out_dir / f"{ts}_{_slug(args.path, 'inpainted')}.png"

        loop = asyncio.get_event_loop()

        t0 = time.monotonic()
        try:
            with vram_lock("inpaint_image"):
                png_bytes = await loop.run_in_executor(
                    None,
                    _sync_inpaint,
                    image,
                    mask,
                    args.prompt,
                    args.negative_prompt,
                    args.steps,
                    args.seed,
                )
        except ImportError as exc:
            return ToolResult(
                ok=False,
                error=f"missing dependency: {exc}. Run: pip install diffusers transformers accelerate torch Pillow",
            )
        except RuntimeError as exc:
            s = str(exc)
            if "CUDA" in s:
                return ToolResult(ok=False, error=f"CUDA error: {s[:200]}")
            return ToolResult(ok=False, error=f"inpainting failed: {s[:200]}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        elapsed = time.monotonic() - t0

        try:
            out_path.write_bytes(png_bytes)
        except OSError as exc:
            return ToolResult(ok=False, error=f"failed to save: {exc}")

        return ToolResult(
            ok=True,
            output=str(out_path),
            metadata={
                "path": str(out_path),
                "source": args.path,
                "mask": args.mask_path,
                "steps": args.steps,
                "seed": args.seed,
                "elapsed_seconds": round(elapsed, 1),
                "size_bytes": len(png_bytes),
                "prompt": args.prompt[:100],
            },
        )
