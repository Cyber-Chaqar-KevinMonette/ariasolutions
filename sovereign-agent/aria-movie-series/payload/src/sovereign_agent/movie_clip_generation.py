"""movie_clip_generation — the single seam the episode render runner calls
to produce one clip, dispatching between "first clip ever" (plain LTX) and
"every clip after" (frame-conditioned continuation).

movie-studio-d Phase 3B (Kevin, 2026-07-28). Reuses the already-live,
four-times-confirmed-safe `_sync_generate_ltx` from
`tools/generate_movie_clip.py` verbatim for the first clip of an episode.
`_sync_generate_ltx_continuation` is NEW — the first real (not just
signature-introspected) use of `LTXConditionPipeline`/`LTXVideoCondition`
in this repo. Same `enable_sequential_cpu_offload()` discipline (the ONLY
offload technique confirmed safe on this 8GB Pascal card — never the
fp8+CUDA-stream recipe that froze the whole machine earlier tonight), and
the SAME proven-safe generation settings (256x256, 9 frames, 30 steps,
guidance_scale=5.0) rather than trusting LTXConditionPipeline's own very
different defaults (704x512, 161 frames, guidance 3).

This function has never generated a real frame as of writing — the plan
explicitly calls for one supervised, monitored real test (mirroring
tonight's own crash-safety discipline) before the render loop is trusted
to run unattended for a real multi-clip chain.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from sovereign_agent.tools.generate_movie_clip import _sync_generate_ltx
from sovereign_agent.vram import vram_lock

__all__ = [
    "DEFAULT_CONDITION_STRENGTH",
    "generate_clip_async",
    "generate_one_clip",
]

DEFAULT_CONDITION_STRENGTH = 1.0  # max continuity on the first real pass; a real creative-control knob to dial down later


def _patch_dynamic_shifting_mu(pipe, *, width: int, height: int, num_frames: int) -> None:
    """Real bug found live (2026-07-28) in diffusers==0.39.0:
    LTXConditionPipeline defines calculate_shift()/mu (copied from the FLUX
    pipeline) but never actually calls it before generating — its scheduler
    unconditionally raises "`mu` must be passed when `use_dynamic_shifting`
    is set to be `True`" the moment use_dynamic_shifting is on, regardless
    of what the caller passes to pipe(). Confirmed by reading
    diffusers/pipelines/ltx/pipeline_ltx_condition.py and
    diffusers/schedulers/scheduling_flow_match_euler_discrete.py directly —
    `calculate_shift` is imported/defined but never referenced anywhere in
    the pipeline's __call__. Worked around here (not by touching the
    installed diffusers version, which the other, already-proven generation
    paths depend on) by wrapping this pipe instance's own
    scheduler.set_timesteps to compute mu itself the same way FLUX does,
    only when the caller didn't already supply one."""
    if not getattr(pipe.scheduler.config, "use_dynamic_shifting", False):
        return
    from diffusers.pipelines.ltx.pipeline_ltx_condition import calculate_shift

    original_set_timesteps = pipe.scheduler.set_timesteps

    # diffusers.pipelines.ltx.pipeline_ltx_condition.retrieve_timesteps
    # introspects scheduler.set_timesteps via inspect.signature(...) to
    # decide whether it "accepts_timesteps" — a *args/**kwargs wrapper
    # hides the real parameter names from that check and falsely reports
    # "does not support custom timestep schedules." Keeping this wrapper's
    # signature explicit (matching FlowMatchEulerDiscreteScheduler's real
    # one) is required, not cosmetic.
    def _set_timesteps_with_mu(num_inference_steps=None, device=None, sigmas=None,
                                mu=None, timesteps=None):
        if mu is None:
            latent_num_frames = (num_frames - 1) // pipe.vae_temporal_compression_ratio + 1
            latent_height = height // pipe.vae_spatial_compression_ratio
            latent_width = width // pipe.vae_spatial_compression_ratio
            image_seq_len = latent_num_frames * latent_height * latent_width
            mu = calculate_shift(image_seq_len)
        return original_set_timesteps(
            num_inference_steps=num_inference_steps, device=device,
            sigmas=sigmas, mu=mu, timesteps=timesteps,
        )

    pipe.scheduler.set_timesteps = _set_timesteps_with_mu


def _sync_generate_ltx_continuation(
    prompt: str, negative_prompt: str, width: int, height: int,
    num_frames: int, steps: int, guidance_scale: float,
    seed: Optional[int], condition_image_path: Path, condition_strength: float,
    out_path: Path,
) -> None:
    import torch
    from PIL import Image
    from diffusers import LTXConditionPipeline
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
    from diffusers.utils import export_to_video

    pipe = LTXConditionPipeline.from_pretrained(
        "Lightricks/LTX-Video", torch_dtype=torch.bfloat16
    )
    pipe.enable_sequential_cpu_offload()
    try:
        pipe.vae.enable_tiling()
    except Exception:  # noqa: BLE001
        pass
    _patch_dynamic_shifting_mu(pipe, width=width, height=height, num_frames=num_frames)

    image = Image.open(condition_image_path).convert("RGB")
    condition = LTXVideoCondition(image=image, frame_index=0, strength=condition_strength)

    gen = torch.Generator().manual_seed(seed) if seed is not None else None
    video = pipe(
        conditions=condition,
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
    ).frames[0]

    export_to_video(video, str(out_path), fps=8)


def _release_gpu_and_cpu_memory() -> None:
    """A real incident (2026-07-28): consecutive calls of this function each
    load a fresh ~10GB LTX pipeline under enable_sequential_cpu_offload(),
    which keeps the WHOLE model resident in system RAM by design (that's
    what makes the layer-by-layer GPU streaming possible). Without an
    explicit release between calls, a second load on top of a still-
    resident first one drove this 15GB-RAM machine into heavy swap
    thrashing that looked like a full system freeze. Force garbage
    collection + empty the CUDA cache after every generation so the next
    call starts from a clean slate — this matters most for the render
    runner, which calls generate_one_clip many times per episode."""
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def generate_one_clip(
    prompt: str, negative_prompt: str, out_path: Path, *,
    condition_image_path: Optional[Path] = None,
    seed: Optional[int] = None,
    width: int = 256, height: int = 256,
    num_frames: int = 9, steps: int = 30, guidance_scale: float = 5.0,
    condition_strength: float = DEFAULT_CONDITION_STRENGTH,
) -> None:
    """Synchronous — runs on the GPU thread. condition_image_path=None means
    this is the very first clip of the episode (no prior frame to carry
    forward); anything else routes through the frame-conditioned path."""
    try:
        if condition_image_path is None:
            _sync_generate_ltx(
                prompt, negative_prompt, width, height, num_frames, steps,
                guidance_scale, seed, out_path,
            )
        else:
            _sync_generate_ltx_continuation(
                prompt, negative_prompt, width, height, num_frames, steps,
                guidance_scale, seed, Path(condition_image_path), condition_strength,
                out_path,
            )
    finally:
        _release_gpu_and_cpu_memory()


async def generate_clip_async(
    prompt: str, negative_prompt: str, out_path: Path, *,
    condition_image_path: Optional[Path] = None,
    seed: Optional[int] = None,
    width: int = 256, height: int = 256,
    num_frames: int = 9, steps: int = 30, guidance_scale: float = 5.0,
    condition_strength: float = DEFAULT_CONDITION_STRENGTH,
) -> None:
    """vram_lock + executor wrapper, same shape as
    GenerateMovieClipTool.execute's own GPU dispatch."""
    loop = asyncio.get_event_loop()
    with vram_lock("generate_movie_clip"):
        await loop.run_in_executor(
            None,
            lambda: generate_one_clip(
                prompt, negative_prompt, out_path,
                condition_image_path=condition_image_path, seed=seed,
                width=width, height=height, num_frames=num_frames, steps=steps,
                guidance_scale=guidance_scale, condition_strength=condition_strength,
            ),
        )
