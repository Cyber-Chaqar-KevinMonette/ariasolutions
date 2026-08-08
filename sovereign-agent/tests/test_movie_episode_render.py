"""Tests for movie_episode_render — the dream.py-style pauseable/resumable/
cap-bounded episode session. Real filesystem (tmp_path), mirroring how
movie_projects.py/movie_series.py are tested directly rather than via fakes
— the runner (Phase B) is where fake-store tests mirroring
test_dream_runner.py's discipline belong, once it exists."""
from __future__ import annotations

import pytest

from sovereign_agent.movie_episode_render import (
    ClipEntry,
    EpisodeCaps,
    EpisodeLocked,
    EpisodeNotFound,
    EpisodeStore,
    ShotEntry,
    count_clip_files_under,
    new_episode_id,
)


def _store(tmp_path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies_work")


def test_new_episode_id_shape():
    eid = new_episode_id("neon-skyline-s01", 1)
    assert eid.startswith("ep-neon-skyline-s01-e01-")


def test_create_get_save_roundtrip(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="neon-skyline", season_id="neon-skyline-s01",
                       episode_number=1, title="Pilot")
    assert ep.status == "active"
    assert ep.shots_completed == 0
    assert store.exists(ep.episode_id)

    loaded = store.get(ep.episode_id)
    assert loaded.title == "Pilot"
    assert loaded.series_slug == "neon-skyline"


def test_create_duplicate_id_raises(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1,
                       title="T", episode_id="ep-fixed-001")
    with pytest.raises(FileExistsError):
        store.create(series_slug="s", season_id="s-s01", episode_number=1,
                      title="T2", episode_id="ep-fixed-001")


def test_get_missing_raises_not_found(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(EpisodeNotFound):
        store.get("ep-does-not-exist-001")


def test_save_persists_shots_and_clips(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.shots.append(ShotEntry(
        shot_number=1, beat="opening", characters_present=["Vex"], status="done",
        clips=[ClipEntry(clip_number=1, path="/tmp/clip1.mp4", quality_status="pass")],
        last_frame_path="/tmp/clip1_last_frame.png",
    ))
    ep.shots_completed = 1
    ep.clips_completed = 1
    ep.last_frame_path = "/tmp/clip1_last_frame.png"
    store.save(ep)

    reloaded = store.get(ep.episode_id)
    assert reloaded.shots_completed == 1
    assert reloaded.shots[0].beat == "opening"
    assert reloaded.shots[0].clips[0].quality_status == "pass"
    assert reloaded.last_frame_path == "/tmp/clip1_last_frame.png"


def test_lock_context_manager_persists_mutations(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    with store.lock(ep.episode_id) as locked:
        locked.status = "paused"
        locked.notes = "paused for the night"
    reloaded = store.get(ep.episode_id)
    assert reloaded.status == "paused"
    assert reloaded.notes == "paused for the night"


def test_lock_does_not_persist_on_exception(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    with pytest.raises(RuntimeError):
        with store.lock(ep.episode_id) as locked:
            locked.status = "halted"
            raise RuntimeError("boom")
    reloaded = store.get(ep.episode_id)
    assert reloaded.status == "active"   # unchanged — exception meant no save


def test_lock_missing_episode_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(EpisodeNotFound):
        with store.lock("ep-nope-001"):
            pass


def test_list_all_filters_by_status(tmp_path):
    store = _store(tmp_path)
    a = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="A")
    b = store.create(series_slug="s", season_id="s-s01", episode_number=2, title="B")
    with store.lock(b.episode_id) as locked:
        locked.status = "completed"

    active = store.list_all(status="active")
    completed = store.list_all(status="completed")
    assert {e.episode_id for e in active} == {a.episode_id}
    assert {e.episode_id for e in completed} == {b.episode_id}


def test_delete_removes_yaml_keeps_work_dir_by_default(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    work = store.work_dir_for(ep.episode_id)
    (work / "clip1.mp4").write_bytes(b"fake")

    assert store.delete(ep.episode_id) is True
    assert not store.exists(ep.episode_id)
    assert work.is_dir()   # work_dir survives unless delete_work_dir=True


def test_delete_with_work_dir(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    work = store.work_dir_for(ep.episode_id)
    (work / "clip1.mp4").write_bytes(b"fake")

    store.delete(ep.episode_id, delete_work_dir=True)
    assert not work.exists()


def test_episode_caps_is_exceeded_max_shots():
    caps = EpisodeCaps(max_shots=3)
    hit, reason = caps.is_exceeded(shots_completed=3, clips_completed=0, elapsed_seconds=0)
    assert hit and "max_shots" in reason
    hit, _ = caps.is_exceeded(shots_completed=2, clips_completed=0, elapsed_seconds=0)
    assert not hit


def test_episode_caps_is_exceeded_max_clips_total():
    caps = EpisodeCaps(max_clips_total=10)
    hit, reason = caps.is_exceeded(shots_completed=0, clips_completed=10, elapsed_seconds=0)
    assert hit and "max_clips_total" in reason


def test_episode_caps_is_exceeded_max_seconds():
    caps = EpisodeCaps(max_seconds=60.0)
    hit, reason = caps.is_exceeded(shots_completed=0, clips_completed=0, elapsed_seconds=61.0)
    assert hit and "max_seconds" in reason


def test_episode_caps_unbounded_when_none_or_zero():
    caps = EpisodeCaps(max_shots=None, max_clips_total=0, max_seconds=None)
    hit, _ = caps.is_exceeded(shots_completed=10_000, clips_completed=10_000, elapsed_seconds=999_999)
    assert not hit


def test_is_terminal_and_caps_check(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T",
                       caps=EpisodeCaps(max_shots=1))
    assert not ep.is_terminal()
    ep.shots_completed = 1
    hit, reason = ep.caps_check()
    assert hit and "max_shots" in reason


def test_count_clip_files_under_skips_quarantine(tmp_path):
    d = tmp_path / "work"
    (d / "shot-1").mkdir(parents=True)
    (d / "shot-1" / "clip1.mp4").write_bytes(b"x")
    (d / "shot-1" / "quarantine").mkdir()
    (d / "shot-1" / "quarantine" / "bad_clip.mp4").write_bytes(b"x")
    assert count_clip_files_under(d) == 1
