"""Tests for movie_episode_render_runner.advance_episode — mirrors
test_dream_runner.py's discipline (drive the runner with controlled state,
no real GPU). The real GPU call (generate_clip_async) is monkeypatched to
write a real synthetic ffmpeg clip; frame extraction (real ffmpeg) and the
quality gate (real PIL) run for real against it — only the expensive LTX
generation itself is faked, so this proves the FULL chaining/retry/
quarantine/pause mechanism against real files, not just mocked booleans."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sovereign_agent.movie_episode_render import EpisodeCaps, EpisodeStore
from sovereign_agent.movie_episode_render_runner import advance_episode
from sovereign_agent.movie_series import Series, create_season, save_series
import sovereign_agent.movie_episode_render_runner as runner_mod

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _store(tmp_path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies_work")


def _make_series_and_season(tmp_path) -> str:
    save_series(Series(title="Neon Skyline"), tmp_path)
    season = create_season("neon-skyline", "Season One", tmp_path)
    return season.season_id


async def _write_colorful_clip(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=8",
         "-frames:v", "8", str(out_path)],
        capture_output=True, timeout=30, check=True,
    )


async def _write_blank_clip(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:duration=1:size=64x64:rate=8",
         "-frames:v", "8", str(out_path)],
        capture_output=True, timeout=30, check=True,
    )


def _add_shot(episode, store, *, target_clips: int = 1, beat: str = "opening shot"):
    from sovereign_agent.movie_episode_render import ShotEntry
    episode.shots.append(ShotEntry(shot_number=len(episode.shots) + 1, beat=beat,
                                    target_clips=target_clips))
    store.save(episode)


def test_paused_episode_refuses_and_writes_nothing(tmp_path, monkeypatch):
    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")
    with store.lock(ep.episode_id) as locked:
        locked.status = "paused"

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == "episode_paused"
    assert result.episode_status == "paused"


@pytest.mark.parametrize("status", ["completed", "exhausted", "halted"])
def test_terminal_episode_refuses(tmp_path, status):
    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")
    with store.lock(ep.episode_id) as locked:
        locked.status = status

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == f"episode_{status}"


def test_no_shots_fails_health_check_instead_of_falsely_completing(tmp_path):
    """Kevin, 2026-07-29: "add a episode verify health and success auto
    checking feature." A zero-shot episode has done ZERO real work — it
    must never be allowed to call itself "completed" just because there
    was nothing left to look at. (Pre-fix this reported "episode_completed";
    that was itself a real instance of the same bad-completion doctrine.)"""
    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == "episode_failed_health_check"
    assert store.get(ep.episode_id).status == "paused"
    assert "zero shots" in store.get(ep.episode_id).notes


def test_cap_pre_check_marks_exhausted(tmp_path):
    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot",
                       caps=EpisodeCaps(max_shots=1))
    _add_shot(ep, store)
    with store.lock(ep.episode_id) as locked:
        locked.shots_completed = 1   # already at the cap before this advance call

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == "episode_exhausted"


def test_first_clip_passes_and_sets_continuity_cursor(tmp_path, monkeypatch):
    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        assert condition_image_path is None   # first clip of the episode — no prior frame
        await _write_colorful_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")
    _add_shot(ep, store, target_clips=1)

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == "shot_done"
    assert result.clip_number == 1

    reloaded = store.get(ep.episode_id)
    assert reloaded.clips_completed == 1
    assert reloaded.shots_completed == 1
    assert reloaded.shots[0].status == "done"
    assert reloaded.last_frame_path is not None
    assert Path(reloaded.last_frame_path).is_file()


def test_advance_augments_the_negative_prompt_with_the_series_safety_level(tmp_path, monkeypatch):
    """Kevin, 2026-07-29: 'add movie production guardrails... add safety
    levels. Which can be applied per series.' Every real clip render gets
    steered away from the series' configured categories — a second,
    always-on layer beyond the beat-text gate at shot-creation time."""
    received = {}
    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        received["negative_prompt"] = negative_prompt
        await _write_colorful_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)   # default safety_level="strict"
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")
    _add_shot(ep, store, target_clips=1)

    advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert "gore" in received["negative_prompt"]
    assert "nudity" in received["negative_prompt"]


def test_genuine_completion_with_a_real_clip_passes_health_check(tmp_path, monkeypatch):
    """Kevin, 2026-07-29: 'add a episode verify health and success auto
    checking feature.' The other half of the poisoned-shot fix: a
    genuinely finished episode (real clip file on disk, really passing)
    must still be allowed to complete — the health check is a safety
    net, not a false-positive generator."""
    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        await _write_colorful_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")
    _add_shot(ep, store, target_clips=1)

    r1 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r1.step_outcome == "shot_done"

    r2 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r2.step_outcome == "episode_completed"
    reloaded = store.get(ep.episode_id)
    assert reloaded.status == "completed"
    assert "health check passed" in reloaded.notes


def test_second_clip_conditions_on_previous_last_frame(tmp_path, monkeypatch):
    seen_condition_paths = []

    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        seen_condition_paths.append(condition_image_path)
        await _write_colorful_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot")
    _add_shot(ep, store, target_clips=2)   # one shot, two chained clips

    r1 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r1.step_outcome == "clip_pass"
    r2 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r2.step_outcome == "shot_done"

    assert seen_condition_paths[0] is None
    assert seen_condition_paths[1] is not None   # second clip carried the first clip's last frame forward


def test_blank_clip_retries_same_slot_without_moving_cursor(tmp_path, monkeypatch):
    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        await _write_blank_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot",
                       caps=EpisodeCaps(max_retries_per_clip=5))
    _add_shot(ep, store, target_clips=1)

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == "clip_retry"
    assert result.clip_number == 1

    reloaded = store.get(ep.episode_id)
    assert reloaded.last_frame_path is None   # cursor never moved on a failure
    assert reloaded.shots[0].clips[-1].quality_status == "failed_retry"
    assert reloaded.shots[0].clips[-1].attempt == 1

    result2 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result2.step_outcome == "clip_retry"
    reloaded2 = store.get(ep.episode_id)
    assert reloaded2.shots[0].clips[-1].clip_number == 1   # SAME slot retried
    assert reloaded2.shots[0].clips[-1].attempt == 2


def test_exhausted_retries_quarantines_and_auto_pauses_episode(tmp_path, monkeypatch):
    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        await _write_blank_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot",
                       caps=EpisodeCaps(max_retries_per_clip=1))
    _add_shot(ep, store, target_clips=1)

    r1 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r1.step_outcome == "clip_retry"
    r2 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r2.step_outcome == "shot_poisoned_episode_paused"
    assert r2.episode_status == "paused"

    reloaded = store.get(ep.episode_id)
    assert reloaded.status == "paused"
    assert reloaded.shots[0].status == "poisoned"
    assert reloaded.shots[0].clips[-1].quality_status == "quarantined"
    # quarantined file moved aside, not left where a real assembly step would find it
    quarantine_dir = Path(reloaded.work_dir) / "shot-001" / "quarantine"
    assert quarantine_dir.is_dir()
    assert any(quarantine_dir.iterdir())

    # A further advance call on a paused episode is refused, not retried again.
    r3 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r3.step_outcome == "episode_paused"


def test_a_poisoned_shot_never_lets_the_episode_report_completed(tmp_path, monkeypatch):
    """Kevin, 2026-07-29: 'it said it completed successfully but the
    folders look empty.' Root cause: the shot-picker only looks for
    ("pending", "in_progress") — a poisoned shot is invisible to it, so
    once the episode got un-paused (simulating the OLD, buggy resume,
    which just flipped status without touching the poisoned shot), the
    next advance call saw "no shots left" and declared the whole episode
    falsely completed. Confirms the fix: it must never do that."""
    async def fake_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        await _write_blank_clip(out_path)
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot",
                       caps=EpisodeCaps(max_retries_per_clip=1))
    _add_shot(ep, store, target_clips=1)

    advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    r2 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r2.step_outcome == "shot_poisoned_episode_paused"

    # Simulate the pre-fix "resume" (un-pause only, poisoned shot untouched).
    with store.lock(ep.episode_id) as reloaded:
        reloaded.status = "active"

    r3 = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert r3.step_outcome != "episode_completed"
    assert r3.step_outcome == "shot_poisoned_episode_paused"
    assert r3.episode_status == "paused"
    final = store.get(ep.episode_id)
    assert final.status == "paused"
    assert "BLOCKED" in final.notes


def test_generation_exception_is_treated_as_a_failed_attempt(tmp_path, monkeypatch):
    async def raising_generate(*, prompt, negative_prompt, out_path, condition_image_path=None, **_):
        raise RuntimeError("CUDA out of memory")
    monkeypatch.setattr(runner_mod, "generate_clip_async", raising_generate)

    season_id = _make_series_and_season(tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id=season_id, episode_number=1, title="Pilot",
                       caps=EpisodeCaps(max_retries_per_clip=3))
    _add_shot(ep, store, target_clips=1)

    result = advance_episode(episode_id=ep.episode_id, store=store, data_dir=tmp_path)
    assert result.step_outcome == "clip_retry"
    assert "generation_error" in result.reason

    reloaded = store.get(ep.episode_id)
    assert reloaded.last_frame_path is None
    assert reloaded.shots[0].clips[-1].quality_status == "failed_retry"
