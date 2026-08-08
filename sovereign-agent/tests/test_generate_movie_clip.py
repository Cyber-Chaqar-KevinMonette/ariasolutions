"""Tests for generate_movie_clip — local LTX-Video generation scoped to a
movie project's workspace.

Real GPU/diffusion calls are monkeypatched to a cheap fake throughout —
same reasoning as test_generate_storyboard_image.py: not safe or fast
enough for CI. The real `_sync_generate_ltx` pipeline was verified live,
by hand, on this exact GPU tonight (four consecutive successful runs with
enable_sequential_cpu_offload(), including a real quality-confirmed clip
at 30 steps/guidance_scale=5.0) — this file proves THIS tool's own
composition/workspace-scoping/error-mapping logic on top of that.
"""
from __future__ import annotations

import pytest

from sovereign_agent.movie_projects import MovieProject, save
from sovereign_agent.tools.generate_movie_clip import GenerateMovieClipTool, _make_step_callback


def test_make_step_callback_translates_diffusers_convention_to_step_total():
    """Kevin, 2026-07-28: 'can we watch the movies generate live???' —
    diffusers calls callback_on_step_end(pipe, step_index, timestep,
    callback_kwargs) and requires the (possibly empty) kwargs dict back;
    this wraps that into a plain (step, total_steps) callback."""
    calls = []
    cb = _make_step_callback(lambda step, total: calls.append((step, total)), total_steps=30)
    fake_kwargs = {"latents": "fake-tensor"}
    result = cb(object(), 0, 999, fake_kwargs)
    assert calls == [(1, 30)]      # step_index is 0-based; reported as 1-based
    assert result is fake_kwargs   # must hand back diffusers' own kwargs dict


def test_make_step_callback_none_is_a_noop():
    assert _make_step_callback(None, total_steps=30) is None


def test_make_step_callback_never_raises_on_a_broken_ui_callback():
    def _boom(step, total):
        raise ValueError("UI blew up")
    cb = _make_step_callback(_boom, total_steps=30)
    result = cb(object(), 5, 999, {"latents": "x"})   # must not raise
    assert result == {"latents": "x"}


def test_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "generate_movie_clip" in _TIER_REGISTRY
    assert _TIER_REGISTRY["generate_movie_clip"].tier == 1


def test_reachable_under_busy_mode_ceiling():
    from sovereign_agent.authority import tools_available_in_mode
    from sovereign_agent.modes import Mode
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in tools_available_in_mode(Mode.BUSY)}
    assert "generate_movie_clip" in names


@pytest.mark.asyncio
async def test_unknown_project_refused(tmp_path):
    tool = GenerateMovieClipTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="ghost", prompt="a red cube"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_vram_failure_is_mapped_honestly(tmp_path, monkeypatch):
    import sovereign_agent.tools.generate_movie_clip as mod

    save(MovieProject(title="Alpha"), tmp_path)

    def fake_generate(*args, **kwargs):
        raise RuntimeError("CUDA out of memory. Tried to allocate 32.00 MiB")
    monkeypatch.setattr(mod, "_sync_generate_ltx", fake_generate)

    tool = GenerateMovieClipTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", prompt="a red cube"), trace_id="t1")
    assert not result.ok
    assert "insufficient_vram" in result.error


@pytest.mark.asyncio
async def test_other_failure_is_generation_failed_not_swallowed(tmp_path, monkeypatch):
    import sovereign_agent.tools.generate_movie_clip as mod

    save(MovieProject(title="Alpha"), tmp_path)

    def fake_generate(*args, **kwargs):
        raise ValueError("num_frames must satisfy the VAE's temporal compression")
    monkeypatch.setattr(mod, "_sync_generate_ltx", fake_generate)

    tool = GenerateMovieClipTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", prompt="a red cube"), trace_id="t1")
    assert not result.ok
    assert "generation_failed" in result.error
    assert "temporal compression" in result.error


@pytest.mark.asyncio
async def test_successful_generation_writes_into_workspace_and_records_asset(
        tmp_path, monkeypatch):
    import sovereign_agent.tools.generate_movie_clip as mod

    save(MovieProject(title="Alpha"), tmp_path)

    def fake_generate(prompt, negative_prompt, width, height, num_frames,
                      steps, guidance_scale, seed, out_path, *, on_step=None):
        out_path.write_bytes(b"\x00\x00\x00\x18ftypmp42-fake-bytes")
    monkeypatch.setattr(mod, "_sync_generate_ltx", fake_generate)

    tool = GenerateMovieClipTool(data_dir=tmp_path)
    result = await tool.execute(
        tool.Args(project_slug="alpha", prompt="a red cube"), trace_id="t1")
    assert result.ok

    from pathlib import Path
    out = Path(result.output["path"])
    assert out.is_file()
    assert out.parent.name == "clips"
    assert out.read_bytes().startswith(b"\x00\x00\x00\x18ftyp")

    manifest = (out.parent.parent / "ASSET_MANIFEST.md").read_text(encoding="utf-8")
    assert out.name in manifest
    assert "clip" in manifest
    assert "generate_movie_clip" in manifest
