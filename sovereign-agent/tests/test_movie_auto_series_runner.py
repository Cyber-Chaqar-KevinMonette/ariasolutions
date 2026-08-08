"""Tests for movie_auto_series_runner.run_auto_series — the bounded,
unattended Auto Series loop.

Only the truly external/heavy calls are faked: the two model-driven
writing calls (movie_series_auto.compose_series_concept/compose_next_beat
— would hit Ollama for real), run_advance_episode (would hit the RAM
gate + GPU for real), and bot_services.pause_for_production/
resume_after_production (would hit REAL systemctl — see the autouse
fixture below; a real incident almost happened here: without it, every
test in this file would genuinely stop/start aria-duty.service on
whatever machine runs the suite). Everything else (movie_projects,
movie_series, EpisodeStore, run_start_episode, run_add_shot) runs for
REAL against tmp_path — cheap, file-based, no GPU — so these tests prove
the loop's actual branching/sequencing logic against real state
transitions, not just mocked booleans."""
from __future__ import annotations

import asyncio

import pytest

import sovereign_agent.bot_services as bot_services_mod
import sovereign_agent.cockpit.movie_generation_actions as actions
import sovereign_agent.movie_series_auto as auto_mod
from sovereign_agent.movie_auto_series_runner import _sanitize_title, run_auto_series
from sovereign_agent.movie_episode_render import ClipEntry, EpisodeStore


@pytest.fixture(autouse=True)
def _never_touch_real_systemctl(monkeypatch):
    """run_auto_series pauses/resumes real bot services around every run.
    This must NEVER hit real systemctl during a test — confirmed as a
    real near-miss: aria-duty.service happened to already be stopped
    when this was first wired, so an early test run's real systemctl
    call was a harmless no-op, but it would NOT have been harmless had
    the service been running."""
    monkeypatch.setattr(bot_services_mod, "pause_for_production",
                        lambda **kw: (False, "mocked — no real systemctl in tests"))
    monkeypatch.setattr(bot_services_mod, "resume_after_production",
                        lambda was_active, **kw: "mocked — no real systemctl in tests")


class _FakeSession:
    def __init__(self, status="active", remaining_minutes=60.0):
        self.status = status
        self._remaining_minutes = remaining_minutes

    def remaining_minutes(self):
        return self._remaining_minutes


class _FakeAutoCrownStore:
    """Injectable stand-in for AutoCrownStore — no real timed session,
    no real disk I/O, full control over armed/expired state per test."""

    def __init__(self, *, active=True, expired=False):
        self._active = active
        self._expired = expired

    def status(self):
        return _FakeSession("active") if self._active else None

    def is_expired(self):
        return self._expired


def _patch_compose_series_concept(monkeypatch, *, title="Auto Test Series", genre="sci-fi",
                                  style="animated", opening_beat="a cube appears"):
    from sovereign_agent.movie_series_auto import SeriesConcept

    calls = []

    async def fake(theme="", *, workspace=None):
        calls.append(theme)
        return SeriesConcept(title=title, logline="a test logline", genre=genre,
                             style=style, opening_beat=opening_beat, raw_reply="")
    monkeypatch.setattr(auto_mod, "compose_series_concept", fake)
    return calls


def _patch_compose_next_beat(monkeypatch, beats=None):
    calls = []
    beats = list(beats or [])

    async def fake(*, series_title, prior_beats, episode_number, workspace=None):
        calls.append((series_title, list(prior_beats), episode_number))
        return beats.pop(0) if beats else f"beat for episode {episode_number}"
    monkeypatch.setattr(auto_mod, "compose_next_beat", fake)
    return calls


async def _fake_advance(episode_id, *, data_dir, sandbox_dir, on_wait=None, on_step=None):
    """A minimal, real-state-mutating stand-in for run_advance_episode —
    no RAM gate, no GPU, but real enough EpisodeStore mutation to drive
    the loop's own branching logic (shot/episode completion detection)."""
    store = EpisodeStore(data_dir / "movie_episodes", sandbox_dir / "movies")
    with store.lock(episode_id) as ep:
        shot = next((s for s in ep.shots if s.status in ("pending", "in_progress")), None)
        if shot is None:
            ep.status = "completed"
            return "episode_completed — episode: completed — no shots left to render"
        shot.status = "in_progress"
        clip_number = len(shot.clips) + 1
        shot.clips.append(ClipEntry(clip_number=clip_number, path="/fake/clip.mp4", attempt=1,
                                    quality_status="pass", quality_reason="fake pass"))
        ep.clips_completed += 1
        outcome = "clip_pass"
        if len(shot.clips) >= shot.target_clips:
            shot.status = "done"
            ep.shots_completed += 1
            outcome = "shot_done"
        return f"{outcome} — shot {shot.shot_number} clip {clip_number} — episode: {ep.status}"


def _patch_advance(monkeypatch):
    calls = []

    async def fake(episode_id, **kw):
        calls.append(episode_id)
        return await _fake_advance(episode_id, **kw)
    monkeypatch.setattr(actions, "run_advance_episode", fake)
    return calls


async def _instant_sleep(_seconds):
    return None


# ── stop conditions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stops_immediately_with_no_active_auto_session(tmp_path):
    result = await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=False),
    )
    assert "Auto session ended" in result


@pytest.mark.asyncio
async def test_pauses_bots_with_the_real_session_eta_and_resumes_on_exit(monkeypatch, tmp_path):
    """Kevin, 2026-07-29: 'make sure the bots automatically pause while
    episodes are being produced... leave an ETA of how long until they
    should be until they are back online.' The ETA must come from the
    REAL armed session's own remaining time, not a guess."""
    pause_calls = []
    resume_calls = []
    monkeypatch.setattr(bot_services_mod, "pause_for_production",
                        lambda **kw: (pause_calls.append(kw) or (True, "stopped")))
    monkeypatch.setattr(bot_services_mod, "resume_after_production",
                        lambda was_active, **kw: resume_calls.append(was_active) or "resumed")

    result = await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),  # a real session with a real ETA
        should_stop=lambda: True,   # ...but stop on the very first loop check
    )
    assert "cancelled" in result
    assert pause_calls == [{"eta_minutes": 60.0}]   # from _FakeSession's default remaining_minutes
    assert resume_calls == [True]


@pytest.mark.asyncio
async def test_stops_immediately_when_should_stop_is_already_true(tmp_path):
    result = await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        should_stop=lambda: True,
    )
    assert "cancelled" in result


@pytest.mark.asyncio
async def test_max_iterations_defensive_cap_stops_the_loop(tmp_path, monkeypatch):
    _patch_compose_series_concept(monkeypatch)
    _patch_compose_next_beat(monkeypatch)
    _patch_advance(monkeypatch)
    result = await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0, max_iterations=1,
    )
    assert "max_iterations=1" in result


# ── series design ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_designs_a_new_series_when_no_project_is_focused(tmp_path, monkeypatch):
    from sovereign_agent.movie_projects import get_focus, list_all

    concept_calls = _patch_compose_series_concept(monkeypatch, title="Auto Test Series")
    _patch_compose_next_beat(monkeypatch)
    _patch_advance(monkeypatch)

    await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0, max_iterations=1,
    )

    assert len(concept_calls) == 1
    projects = list_all(tmp_path)
    assert any(p.title == "Auto Test Series" for p in projects)
    assert get_focus(tmp_path).slug == "auto-test-series"


@pytest.mark.asyncio
async def test_reuses_the_already_focused_project_instead_of_designing_a_new_one(tmp_path, monkeypatch):
    from sovereign_agent.movie_projects import MovieProject, save as save_project, set_focus

    save_project(MovieProject(title="Already Focused"), tmp_path)
    set_focus("already-focused", "testing", tmp_path)

    concept_calls = _patch_compose_series_concept(monkeypatch)
    _patch_compose_next_beat(monkeypatch)
    _patch_advance(monkeypatch)

    await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0, max_iterations=1,
    )
    assert concept_calls == []   # never designed a NEW series


@pytest.mark.asyncio
async def test_invalid_genre_and_style_from_the_model_fall_back_honestly(tmp_path, monkeypatch):
    from sovereign_agent.movie_projects import list_all

    _patch_compose_series_concept(monkeypatch, genre="nonsense-genre", style="nonsense-style")
    _patch_compose_next_beat(monkeypatch)
    _patch_advance(monkeypatch)

    await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0, max_iterations=1,
    )
    proj = list_all(tmp_path)[0]
    assert proj.genre == "short-film"
    assert proj.style == "animated"


def test_sanitize_title_strips_illegal_characters():
    assert _sanitize_title("The Last: Lighthouse!", fallback="Auto Series") == "The Last Lighthouse"


def test_sanitize_title_falls_back_when_nothing_survives():
    assert _sanitize_title("::::", fallback="Auto Series") == "Auto Series"


# ── episode + shot sequencing ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_starts_an_episode_with_the_composed_opening_beat(tmp_path, monkeypatch):
    _patch_compose_series_concept(monkeypatch, opening_beat="a cube slowly rotates")
    _patch_compose_next_beat(monkeypatch)
    _patch_advance(monkeypatch)

    from sovereign_agent.movie_episode_render import EpisodeStore
    from sovereign_agent.movie_series import get_episode_focus

    await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0, max_iterations=1,
    )
    focus = get_episode_focus(tmp_path)
    ep = EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies").get(focus.episode_id)
    assert ep.shots[0].beat == "a cube slowly rotates"


@pytest.mark.asyncio
async def test_queues_the_next_shot_before_the_current_one_runs_dry(tmp_path, monkeypatch):
    _patch_compose_series_concept(monkeypatch, opening_beat="shot one")
    beat_calls = _patch_compose_next_beat(monkeypatch, beats=["shot two"])
    advance_calls = _patch_advance(monkeypatch)

    from sovereign_agent.movie_episode_render import EpisodeStore
    from sovereign_agent.movie_series import get_episode_focus

    # target_clips defaults to DEFAULT_TARGET_CLIPS (5) via run_start_episode.
    # After 4 advances the current shot has 4/5 clips (1 left); the 5th
    # iteration's pre-check (which runs BEFORE that iteration's advance
    # call) is where the next shot actually gets queued.
    await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0, max_iterations=5,
    )
    focus = get_episode_focus(tmp_path)
    ep = EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies").get(focus.episode_id)
    assert len(ep.shots) == 2
    assert ep.shots[1].beat == "shot two"
    assert len(advance_calls) == 5
    # the beat for shot two must have been composed with shot one's beat as history
    assert any("shot one" in prior for _, prior, _ in beat_calls)


@pytest.mark.asyncio
async def test_starts_a_new_episode_after_the_current_one_completes(tmp_path, monkeypatch):
    _patch_compose_series_concept(monkeypatch, opening_beat="ep1 opener")
    beat_calls = _patch_compose_next_beat(monkeypatch, beats=["ep2 opener"])
    _patch_advance(monkeypatch)

    from sovereign_agent.cockpit.movie_generation_actions import DEFAULT_TARGET_CLIPS
    from sovereign_agent.movie_episode_render import EpisodeStore
    from sovereign_agent.movie_series import get_episode_focus

    # shots_per_episode=1: never queue a second shot, so episode 1's single
    # shot runs to completion (DEFAULT_TARGET_CLIPS clips: iterations
    # 1-5), one more iteration for advance_episode itself to notice no
    # shots remain and flip the episode to "completed" (iteration 6), then
    # one more for the runner to see that terminal state and start episode
    # 2 (iteration 7).
    await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=_instant_sleep, clip_gap_seconds=0.0,
        shots_per_episode=1, max_iterations=DEFAULT_TARGET_CLIPS + 2,
    )
    from sovereign_agent.movie_projects import get_focus, load_by_slug
    proj_slug = get_focus(tmp_path).slug
    store = EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies")
    episode_ids = [p.stem for p in (tmp_path / "movie_episodes").glob("*.yaml")]
    episodes = [store.get(eid) for eid in episode_ids]
    assert len(episodes) == 2
    second = next(e for e in episodes if e.episode_number == 2)
    assert second.shots[0].beat == "ep2 opener"


# ── graceful sleep ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sleeps_between_clips_and_stops_mid_sleep_when_cancelled(tmp_path, monkeypatch):
    _patch_compose_series_concept(monkeypatch)
    _patch_compose_next_beat(monkeypatch)
    _patch_advance(monkeypatch)

    sleep_calls = []
    stop_after_first_sleep = {"n": 0}

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    def should_stop():
        return len(sleep_calls) >= 1

    clock_value = {"t": 0.0}
    def fake_clock():
        clock_value["t"] += 1.0
        return clock_value["t"]

    result = await run_auto_series(
        data_dir=tmp_path, sandbox_dir=tmp_path,
        auto_crown_store=_FakeAutoCrownStore(active=True),
        sleep=fake_sleep, clock=fake_clock, clip_gap_seconds=5.0, poll_seconds=1.0,
        should_stop=should_stop,
    )
    assert len(sleep_calls) >= 1
    assert "cancelled" in result
