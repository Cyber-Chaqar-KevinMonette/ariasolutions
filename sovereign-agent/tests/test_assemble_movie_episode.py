"""Tests for assemble_movie_episode — real ffmpeg concat of chained clips
into one playable file. Uses real synthetic ffmpeg clips (same
`ffmpeg -f lavfi testsrc` idiom test_movie_video_continuity.py already
uses), not hand-crafted fixtures."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from sovereign_agent.movie_episode_render import ClipEntry, EpisodeStore, ShotEntry
from sovereign_agent.tools.assemble_movie_episode import AssembleMovieEpisodeTool

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _store(tmp_path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies_work")


def _make_synthetic_clip(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=8",
         "-frames:v", "8", str(path)],
        capture_output=True, timeout=30, check=True,
    )


def _episode_with_two_pass_clips(store, tmp_path, *, status="completed"):
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    _make_synthetic_clip(clip1)
    _make_synthetic_clip(clip2)
    ep.shots.append(ShotEntry(
        shot_number=1, beat="opening", target_clips=2,
        clips=[
            ClipEntry(clip_number=1, path=str(clip1), quality_status="pass"),
            ClipEntry(clip_number=2, path=str(clip2), quality_status="pass"),
        ],
        status="done",
    ))
    ep.status = status
    ep.shots_completed = 1
    ep.clips_completed = 2
    store.save(ep)
    return ep


@pytest.mark.asyncio
async def test_assemble_unknown_episode_fails_cleanly(tmp_path):
    store = _store(tmp_path)
    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    result = await tool.execute(tool.Args(episode_id="ep-nope-001"), trace_id="t")
    assert result.ok is False
    assert "unknown_episode" in result.error


@pytest.mark.asyncio
async def test_assemble_refuses_non_completed_episode_without_allow_partial(tmp_path):
    store = _store(tmp_path)
    ep = _episode_with_two_pass_clips(store, tmp_path, status="active")
    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    result = await tool.execute(tool.Args(episode_id=ep.episode_id), trace_id="t")
    assert result.ok is False
    assert "episode_not_completed" in result.error


@pytest.mark.asyncio
async def test_assemble_partial_allowed_when_flagged(tmp_path):
    store = _store(tmp_path)
    ep = _episode_with_two_pass_clips(store, tmp_path, status="active")
    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    result = await tool.execute(tool.Args(episode_id=ep.episode_id, allow_partial=True), trace_id="t")
    assert result.ok is True, result.error
    assert result.output["clip_count"] == 2


@pytest.mark.asyncio
async def test_assemble_completed_episode_produces_a_real_playable_file(tmp_path):
    store = _store(tmp_path)
    ep = _episode_with_two_pass_clips(store, tmp_path, status="completed")
    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    result = await tool.execute(tool.Args(episode_id=ep.episode_id), trace_id="t")
    assert result.ok is True, result.error

    from pathlib import Path
    out = Path(result.output["path"])
    assert out.is_file() and out.stat().st_size > 0

    # confirm it's a real, decodable video (not just a non-empty file)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(out)],
        capture_output=True, timeout=30,
    )
    assert probe.returncode == 0


@pytest.mark.asyncio
async def test_assemble_skips_quarantined_and_failed_clips(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    good = tmp_path / "good.mp4"
    _make_synthetic_clip(good)
    ep.shots.append(ShotEntry(
        shot_number=1, beat="b", target_clips=1,
        clips=[
            ClipEntry(clip_number=1, path=str(tmp_path / "bad.mp4"), quality_status="quarantined"),
            ClipEntry(clip_number=1, path=str(tmp_path / "bad2.mp4"), quality_status="failed_retry"),
            ClipEntry(clip_number=2, path=str(good), quality_status="pass"),
        ],
        status="done",
    ))
    ep.status = "completed"
    store.save(ep)

    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    result = await tool.execute(tool.Args(episode_id=ep.episode_id), trace_id="t")
    assert result.ok is True, result.error
    assert result.output["clip_count"] == 1   # only the one real "pass" clip


@pytest.mark.asyncio
async def test_assemble_no_pass_clips_fails_cleanly(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.status = "completed"
    store.save(ep)

    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    result = await tool.execute(tool.Args(episode_id=ep.episode_id), trace_id="t")
    assert result.ok is False
    assert "no_clips_to_assemble" in result.error


@pytest.mark.asyncio
async def test_assemble_records_asset_manifest_entry(tmp_path):
    store = _store(tmp_path)
    ep = _episode_with_two_pass_clips(store, tmp_path, status="completed")
    tool = AssembleMovieEpisodeTool(data_dir=tmp_path, work_root=tmp_path / "movies_work")
    await tool.execute(tool.Args(episode_id=ep.episode_id), trace_id="t")

    from pathlib import Path
    manifest = Path(ep.work_dir) / "ASSET_MANIFEST.md"
    assert manifest.is_file()
    assert "episode_cut" in manifest.read_text(encoding="utf-8")
