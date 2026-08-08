"""Tests for movie_episode_health — real, file-level episode verification.
Real ffmpeg clips and real ffprobe calls throughout (skipped if ffmpeg
isn't installed), mirroring test_movie_episode_render_runner.py's own
"don't just mock booleans" discipline for exactly this kind of check."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sovereign_agent.movie_episode_health import (
    ClipHealthIssue,
    probe_clip,
    verify_episode_health,
)
from sovereign_agent.movie_episode_render import ClipEntry, EpisodeStore, ShotEntry

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="ffmpeg/ffprobe not installed")


def _store(tmp_path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies_work")


def _write_real_clip(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=8",
         "-frames:v", "8", str(out_path)],
        capture_output=True, timeout=30, check=True,
    )


# ── probe_clip ────────────────────────────────────────────────────────────


def test_probe_clip_passes_a_real_video(tmp_path):
    clip = tmp_path / "real.mp4"
    _write_real_clip(clip)
    ok, detail = probe_clip(clip)
    assert ok is True
    assert "frame" in detail


def test_probe_clip_fails_a_missing_file(tmp_path):
    ok, detail = probe_clip(tmp_path / "nope.mp4")
    assert ok is False
    assert "not found" in detail


def test_probe_clip_fails_an_empty_file(tmp_path):
    clip = tmp_path / "empty.mp4"
    clip.write_bytes(b"")
    ok, detail = probe_clip(clip)
    assert ok is False
    assert "empty" in detail


def test_probe_clip_fails_garbage_bytes_that_arent_a_real_video(tmp_path):
    clip = tmp_path / "garbage.mp4"
    clip.write_bytes(b"this is not a real video file, just plain text bytes")
    ok, detail = probe_clip(clip)
    assert ok is False


def test_probe_clip_never_raises_when_ffprobe_is_missing(tmp_path, monkeypatch):
    clip = tmp_path / "real.mp4"
    _write_real_clip(clip)
    monkeypatch.setattr("shutil.which", lambda name: None)
    ok, detail = probe_clip(clip)
    assert ok is False
    assert "not installed" in detail


# ── verify_episode_health ────────────────────────────────────────────────


def _make_episode(tmp_path, series_slug="s"):
    store = _store(tmp_path)
    return store, store.create(series_slug=series_slug, season_id="s-s01", episode_number=1, title="T")


def test_healthy_episode_with_real_clips_passes(tmp_path):
    store, ep = _make_episode(tmp_path)
    clip_path = Path(ep.work_dir) / "shot-001" / "clip-001-attempt-01.mp4"
    _write_real_clip(clip_path)
    ep.shots.append(ShotEntry(
        shot_number=1, beat="b", target_clips=1, status="done",
        clips=[ClipEntry(clip_number=1, path=str(clip_path), quality_status="pass")],
    ))
    store.save(ep)

    report = verify_episode_health(ep)
    assert report.healthy is True
    assert report.clips_verified == 1
    assert report.issues == []
    assert "passed" in report.summary()


def test_a_poisoned_shot_always_makes_the_episode_unhealthy(tmp_path):
    """The exact real incident: a poisoned shot must never be silently
    treated as 'nothing to check here.'"""
    store, ep = _make_episode(tmp_path)
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=5, status="poisoned"))
    store.save(ep)

    report = verify_episode_health(ep)
    assert report.healthy is False
    assert any("poisoned" in str(i) for i in report.issues)


def test_a_done_shot_with_too_few_passing_clips_is_unhealthy(tmp_path):
    store, ep = _make_episode(tmp_path)
    clip_path = Path(ep.work_dir) / "shot-001" / "clip-001-attempt-01.mp4"
    _write_real_clip(clip_path)
    ep.shots.append(ShotEntry(
        shot_number=1, beat="b", target_clips=3, status="done",   # says done, only 1/3 actually passed
        clips=[ClipEntry(clip_number=1, path=str(clip_path), quality_status="pass")],
    ))
    store.save(ep)

    report = verify_episode_health(ep)
    assert report.healthy is False
    assert any("only 1/3" in str(i) for i in report.issues)


def test_a_done_shot_whose_clip_file_is_missing_is_unhealthy(tmp_path):
    """The exact real bug: bookkeeping said 'pass' but the file was never
    actually written (the torch import failed before ffmpeg ever ran)."""
    store, ep = _make_episode(tmp_path)
    missing_path = Path(ep.work_dir) / "shot-001" / "clip-001-attempt-01.mp4"
    ep.shots.append(ShotEntry(
        shot_number=1, beat="b", target_clips=1, status="done",
        clips=[ClipEntry(clip_number=1, path=str(missing_path), quality_status="pass")],
    ))
    store.save(ep)

    report = verify_episode_health(ep)
    assert report.healthy is False
    assert any("not found" in str(i) for i in report.issues)


def test_an_episode_with_zero_shots_is_unhealthy(tmp_path):
    _, ep = _make_episode(tmp_path)
    report = verify_episode_health(ep)
    assert report.healthy is False
    assert any("zero shots" in str(i) for i in report.issues)


def test_pending_and_in_progress_shots_are_not_held_to_the_done_bar(tmp_path):
    """A shot still in flight isn't a health problem yet — only shots
    claiming to be finished get checked."""
    store, ep = _make_episode(tmp_path)
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=5, status="pending"))
    ep.shots.append(ShotEntry(shot_number=2, beat="c", target_clips=5, status="in_progress"))
    store.save(ep)

    report = verify_episode_health(ep)
    assert report.healthy is True
    assert report.issues == []


def test_injected_probe_is_used_instead_of_the_real_ffprobe(tmp_path):
    store, ep = _make_episode(tmp_path)
    ep.shots.append(ShotEntry(
        shot_number=1, beat="b", target_clips=1, status="done",
        clips=[ClipEntry(clip_number=1, path="/fake/never/exists.mp4", quality_status="pass")],
    ))
    store.save(ep)

    calls = []
    def fake_probe(path):
        calls.append(path)
        return True, "fake pass"

    report = verify_episode_health(ep, probe=fake_probe)
    assert report.healthy is True
    assert len(calls) == 1
