"""
image_generate.py — local image generation for Aria

Tier 1 tool (sandbox write) — generates images using local diffusion models
and saves them to data_dir/images/generated/.

Engine priority:
  1. FLUX.1-schnell via diffusers (state-of-the-art open-source, ~6GB VRAM)
  2. SDXL-Turbo (fast, 4-step, ~5.5GB VRAM)
  3. Stable Diffusion 2.1 (fallback, ~3.5GB VRAM)

VRAM strategy: uses vram_lock() to serialize with qwen3:8b. The Ollama
model unloads from VRAM when idle, freeing ~5.2GB for generation.
GPU work runs in a thread executor so the event loop stays responsive.

Saves to: <data_dir>/images/generated/<timestamp>_<slug>.png
Returns the absolute path so analyze_image can be called on the result.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from sovereign_agent.config import SETTINGS
from sovereign_agent.vram import SAFETY_FLOOR_MB, read_vram, vram_lock

from .base import Tool, ToolResult


_DEFAULT_MODEL = os.environ.get("AGENT_IMAGE_GEN_MODEL", "sdxl-turbo")
_VALID_MODELS = {"flux-schnell", "sdxl-turbo", "sd21"}
_MODEL_VRAM_MB = {
    "flux-schnell": 6144,
    "sdxl-turbo": 5500,
    "sd21": 3500,
}
_HF_REPOS = {
    "flux-schnell": "black-forest-labs/FLUX.1-schnell",
    "sdxl-turbo": "stabilityai/sdxl-turbo",
    "sd21": "stabilityai/stable-diffusion-2-1",
}


def _slug(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "_", s).strip("_")
    return s[:maxlen]


# ── synchronous generation functions (called in thread executor) ─────────────


def _sync_generate_flux(
    prompt: str, width: int, height: int, steps: int, seed: Optional[int]
) -> bytes:
    import torch
    from diffusers import FluxPipeline

    pipe = FluxPipeline.from_pretrained(
        _HF_REPOS["flux-schnell"],
        torch_dtype=torch.bfloat16,
    )
    pipe.enable_model_cpu_offload()

    gen = torch.Generator().manual_seed(seed) if seed is not None else None
    image = pipe(
        prompt,
        width=width,
        height=height,
        guidance_scale=0.0,  # FLUX-schnell is guidance-free
        num_inference_steps=steps,
        generator=gen,
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _sync_generate_sdxl_turbo(
    prompt: str, width: int, height: int, steps: int, seed: Optional[int]
) -> bytes:
    import torch
    from diffusers import AutoPipelineForText2Image

    pipe = AutoPipelineForText2Image.from_pretrained(
        _HF_REPOS["sdxl-turbo"],
        torch_dtype=torch.float16,
        variant="fp16",
    )
    # real-bug-d (2026-07-28): bare .to("cuda") left the WHOLE pipeline
    # (UNet + 2 text encoders + VAE, all fp16) resident at once on this
    # 8GB card — confirmed OOM live, at the deprecated fp32 VAE-upcast
    # step specifically ("Tried to allocate 20.00 MiB" with <100MiB
    # free). enable_model_cpu_offload (same technique _sync_generate_
    # flux already uses) frees each component back to CPU between
    # steps instead of keeping everything on GPU simultaneously.
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_slicing()

    gen = torch.Generator(device="cuda").manual_seed(seed) if seed is not None else None
    image = pipe(
        prompt=prompt,
        num_inference_steps=min(steps, 4),  # SDXL-Turbo is 1-4 step
        guidance_scale=0.0,
        width=width,
        height=height,
        generator=gen,
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _sync_generate_sd21(
    prompt: str, width: int, height: int, steps: int, seed: Optional[int]
) -> bytes:
    import torch
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

    scheduler = DPMSolverMultistepScheduler.from_pretrained(
        _HF_REPOS["sd21"], subfolder="scheduler"
    )
    pipe = StableDiffusionPipeline.from_pretrained(
        _HF_REPOS["sd21"],
        torch_dtype=torch.float16,
        scheduler=scheduler,
    )
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_slicing()

    gen = torch.Generator(device="cuda").manual_seed(seed) if seed is not None else None
    image = pipe(
        prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
        generator=gen,
    ).images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


_SYNC_FNS = {
    "flux-schnell": _sync_generate_flux,
    "sdxl-turbo": _sync_generate_sdxl_turbo,
    "sd21": _sync_generate_sd21,
}


# ── tool ─────────────────────────────────────────────────────────────────────


class GenerateImageTool(Tool):
    """Generate an image from a text prompt using local diffusion models.

    Uses FLUX.1-schnell by default (best open-source quality). Serializes
    via vram_lock so generation never competes with qwen3:8b for the GTX 1070's
    8GB. GPU work runs in a thread executor so the cockpit stays responsive.

    Returns the absolute path to the saved PNG so you can immediately call
    analyze_image or show it to the operator.

    Prompt tips:
      - Specific: "a red apple on white marble, studio lighting"
      - Style: "oil painting", "digital art", "photorealistic", "sketch"
      - Quality: "8k", "highly detailed", "professional photography"
      - Negative prompt: what to avoid ("blurry, text, watermark")

    For the GTX 1070 (8GB), 512×512 takes ~20-40s. 768×768 may OOM on flux;
    use sd21 for larger sizes on constrained VRAM.
    """

    name = "generate_image"
    tier = 1  # Tier 1: writes files to sandbox (data_dir/images/)
    description = (
        "Generate an image from a text prompt using local FLUX.1-schnell diffusion. "
        "Saves PNG to data_dir/images/generated/ and returns the path. "
        "Args: prompt (required), negative_prompt, model (flux-schnell/sdxl-turbo/sd21), "
        "width (256-1024), height (256-1024), steps (1-50), seed. "
        "VRAM-serialized. ~20-40s on GTX 1070 at 512×512."
    )
    failure_modes = (
        "diffusers/torch not installed — pip install diffusers transformers accelerate",
        "model weights not cached — first run downloads ~6GB automatically",
        "insufficient VRAM — close Ollama or use sd21 (lower VRAM)",
        "CUDA unavailable — requires NVIDIA GPU with CUDA drivers",
        "disk full — check data_dir/images/generated/",
    )

    class Args(BaseModel):
        prompt: str = Field(description="Text description of the image to generate.")
        negative_prompt: str = Field(
            default="blurry, low quality, watermark, text, signature, ugly, deformed",
            description="What to avoid in the image.",
        )
        model: str = Field(
            default=_DEFAULT_MODEL,
            description=(
                f"Model: flux-schnell (best, 6GB), sdxl-turbo (fast, 5.5GB), "
                f"sd21 (reliable, 3.5GB). Default: {_DEFAULT_MODEL}"
            ),
        )
        width: int = Field(default=512, ge=256, le=1024, description="Width in pixels.")
        height: int = Field(default=512, ge=256, le=1024, description="Height in pixels.")
        steps: int = Field(
            default=4, ge=1, le=50,
            description="Inference steps. 4 is fast/good for flux/sdxl-turbo; 20 for sd21.",
        )
        seed: Optional[int] = Field(default=None, description="Seed for reproducibility.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        model = args.model.lower()
        if model not in _VALID_MODELS:
            return ToolResult(
                ok=False,
                error=f"unknown model {model!r}. valid: {', '.join(sorted(_VALID_MODELS))}",
            )

        # Pre-flight VRAM check
        try:
            snap = read_vram()
            required = _MODEL_VRAM_MB[model]
            if snap.free_mb < required - SAFETY_FLOOR_MB:
                return ToolResult(
                    ok=False,
                    error=(
                        f"insufficient VRAM: need ~{required}MB free, "
                        f"have {snap.free_mb}MB. "
                        f"Try closing Ollama or use model=sd21 (~3.5GB)."
                    ),
                )
        except Exception:
            pass  # VRAM read failed; try anyway

        data_dir = SETTINGS.paths.data_dir
        if data_dir is None:
            return ToolResult(ok=False, error="data_dir not configured")

        out_dir = Path(data_dir) / "images" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = int(time.time())
        out_path = out_dir / f"{ts}_{_slug(args.prompt)}.png"

        sync_fn = _SYNC_FNS[model]
        loop = asyncio.get_event_loop()

        t0 = time.monotonic()
        try:
            with vram_lock("generate_image"):
                png_bytes = await loop.run_in_executor(
                    None,
                    sync_fn,
                    args.prompt,
                    args.width,
                    args.height,
                    args.steps,
                    args.seed,
                )
        except ImportError as exc:
            return ToolResult(
                ok=False,
                error=(
                    f"missing dependency: {exc}. "
                    "Run: pip install diffusers transformers accelerate torch"
                ),
            )
        except RuntimeError as exc:
            s = str(exc)
            if "CUDA" in s or "cuda" in s:
                return ToolResult(
                    ok=False,
                    error=f"CUDA error: {s[:300]}. Check VRAM and driver.",
                )
            return ToolResult(ok=False, error=f"generation failed: {s[:300]}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        elapsed = time.monotonic() - t0

        try:
            out_path.write_bytes(png_bytes)
        except OSError as exc:
            return ToolResult(ok=False, error=f"failed to save image: {exc}")

        return ToolResult(
            ok=True,
            output=str(out_path),
            metadata={
                "path": str(out_path),
                "model": model,
                "width": args.width,
                "height": args.height,
                "steps": args.steps,
                "seed": args.seed,
                "elapsed_seconds": round(elapsed, 1),
                "size_bytes": len(png_bytes),
                "prompt": args.prompt[:120],
            },
        )
