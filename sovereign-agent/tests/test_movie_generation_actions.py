"""Tests for movie_generation_actions — the shared RAM-gated action layer
both the Movie Studio modal and the new movie pane call into.

Heavy-tool calls (storyboard/clip/advance) are monkeypatched to fakes so
these tests never touch the GPU; RAM gate itself is monkeypatched too for
the "refused" paths. Episode lifecycle (start/pause/resume/assemble) uses
real EpisodeStore/movie_series against tmp_path — cheap, local, and more
valuable tested for real than mocked.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from sovereign_agent import ram_gate
from sovereign_agent.cockpit import movie_generation_actions as actions
from sovereign_agent.movie_episode_render import ClipEntry, EpisodeStore, ShotEntry
from sovereign_agent.movie_projects import MovieProject, save as save_project


# ── observability wiring (Kevin, 2026-07-28: "I am not getting anything
# on the observability side") ───────────────────────────────────────────


def test_emit_calls_the_real_events_module_with_movie_plane(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "sovereign_agent.events.emit_event",
        lambda flag, *, plane, trace_id, payload=None, **kw: calls.append((flag, plane, trace_id, payload)),
    )
    actions._emit("movie-clip-start-d", trace_id="movie:alpha", prompt="a red cube")
    assert calls == [("movie-clip-start-d", "movie", "movie:alpha", {"prompt": "a red cube"})]


def test_emit_never_raises_when_events_module_is_broken(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("events.jsonl unwritable")
    monkeypatch.setattr("sovereign_agent.events.emit_event", _boom)
    actions._emit("movie-clip-start-d", trace_id="movie:alpha")   # must not raise


def test_wrap_on_step_for_events_ticks_at_first_last_and_every_n(monkeypatch):
    emitted = []
    monkeypatch.setattr(actions, "_emit", lambda flag, *, trace_id, **kw: emitted.append(kw["step"]))
    inner_calls = []
    wrapped = actions._wrap_on_step_for_events(lambda s, t: inner_calls.append(s), trace_id="t", every=5)
    for step in range(1, 31):
        wrapped(step, 30)
    assert emitted == [1, 5, 10, 15, 20, 25, 30]   # first, every-5, and last — not every single step
    assert inner_calls == list(range(1, 31))        # the caller's own on_step still fires every time
from sovereign_agent.movie_series import load_series_by_slug


# ── content safety levels (Kevin, 2026-07-29: "add movie production
# guardrails also so movies are social media platform friendly... add
# safety levels. Which can be applied per series") ─────────────────────────


@pytest.mark.asyncio
async def test_run_generate_storyboard_refuses_unsafe_prompt_before_ram_gate(tmp_path, monkeypatch):
    from sovereign_agent.movie_series import Series, save_series
    save_series(Series(title="Kids Show", safety_level="strict"), tmp_path)

    ram_gate_called = []
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: ram_gate_called.append(1) or (True, ""))

    result = await actions.run_generate_storyboard(
        "kids-show", "graphic gore and dismemberment", data_dir=tmp_path)
    assert "refused" in result
    assert "gore" in result
    assert ram_gate_called == []   # the safety check runs BEFORE the RAM gate — no wasted wait


@pytest.mark.asyncio
async def test_run_generate_storyboard_allows_a_clean_prompt_at_strict(tmp_path, monkeypatch):
    from sovereign_agent.movie_series import Series, save_series
    save_series(Series(title="Kids Show", safety_level="strict"), tmp_path)
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))

    from sovereign_agent.tools.base import ToolResult
    class _FakeTool:
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
            self.Args = _A
        async def execute(self, args, *, trace_id):
            return ToolResult(ok=True, output={"path": "/fake/storyboard.png"})
    import sovereign_agent.tools.generate_storyboard_image as real_mod
    monkeypatch.setattr(real_mod, "GenerateStoryboardImageTool", _FakeTool)

    result = await actions.run_generate_storyboard("kids-show", "a small red cube", data_dir=tmp_path)
    assert "generated" in result


@pytest.mark.asyncio
async def test_run_generate_clip_refuses_unsafe_prompt_at_the_series_own_level(tmp_path, monkeypatch):
    from sovereign_agent.movie_series import Series, save_series
    save_series(Series(title="Adult Only", safety_level="moderate"), tmp_path)
    ram_gate_called = []
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: ram_gate_called.append(1) or (True, ""))

    result = await actions.run_generate_clip(
        "adult-only", "graphic violence and dismemberment", data_dir=tmp_path)
    assert "refused" in result
    assert ram_gate_called == []


@pytest.mark.asyncio
async def test_run_generate_clip_allows_mild_action_at_moderate_but_not_strict(tmp_path, monkeypatch):
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))
    from sovereign_agent.movie_series import Series, save_series
    save_series(Series(title="Strict Show", safety_level="strict"), tmp_path)
    save_series(Series(title="Moderate Show", safety_level="moderate"), tmp_path)

    prompt = "a dramatic sword fight and a building explosion"
    strict_result = await actions.run_generate_clip("strict-show", prompt, data_dir=tmp_path)
    assert "refused" not in strict_result   # neither "sword fight" nor "explosion" is in ANY blocklist

    moderate_result = await actions.run_generate_clip("moderate-show", prompt, data_dir=tmp_path)
    assert "refused" not in moderate_result


@pytest.mark.asyncio
async def test_run_generate_clip_passes_an_augmented_negative_prompt_to_the_tool(tmp_path, monkeypatch):
    from sovereign_agent.movie_series import Series, save_series
    save_series(Series(title="Safety Test Show", safety_level="strict"), tmp_path)
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))

    from sovereign_agent.tools.base import ToolResult
    received = {}
    class _FakeTool:
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
                negative_prompt: str = ""
            self.Args = _A
        async def execute(self, args, *, trace_id, on_step=None):
            received["negative_prompt"] = args.negative_prompt
            return ToolResult(ok=True, output={"path": "/fake/clip.mp4"})
    import sovereign_agent.tools.generate_movie_clip as real_mod
    monkeypatch.setattr(real_mod, "GenerateMovieClipTool", _FakeTool)

    await actions.run_generate_clip("safety-test-show", "a red cube spinning", data_dir=tmp_path)
    assert "gore" in received["negative_prompt"]
    assert "nudity" in received["negative_prompt"]
    assert "worst quality" in received["negative_prompt"]   # base negative terms preserved


@pytest.mark.asyncio
async def test_run_start_episode_refuses_an_unsafe_beat(tmp_path):
    from sovereign_agent.movie_projects import MovieProject, save as save_project
    save_project(MovieProject(title="Guarded Show"), tmp_path)

    result = await actions.run_start_episode(
        "guarded-show", beat="graphic gore and torture", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "cannot start episode" in result
    assert "gore" in result

    from sovereign_agent.movie_episode_render import EpisodeStore
    store = EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies")
    assert list((tmp_path / "movie_episodes").glob("*.yaml")) == []   # no orphaned episode left behind


@pytest.mark.asyncio
async def test_run_add_shot_refuses_an_unsafe_beat_at_the_episode_own_series_level(tmp_path):
    from sovereign_agent.movie_series import Series, save_series
    save_series(Series(title="Guarded Show", safety_level="strict"), tmp_path)
    store = _store(tmp_path)
    ep = store.create(series_slug="guarded-show", season_id="guarded-show-s01", episode_number=1, title="T")

    result = await actions.run_add_shot(
        ep.episode_id, "full nudity and porn", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "refused" in result
    assert "nudity" in result or "porn" in result
    assert store.get(ep.episode_id).shots == []


# ── storyboard / clip (RAM-gated, tool monkeypatched) ──────────────────────


@pytest.mark.asyncio
async def test_run_generate_storyboard_ram_refused_never_calls_tool(monkeypatch):
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (False, "RAM never cleared"))

    called = []
    class _BoomTool:
        def __init__(self, data_dir=None):
            called.append("constructed")

    import sovereign_agent.tools.generate_storyboard_image as real_mod
    monkeypatch.setattr(real_mod, "GenerateStoryboardImageTool", _BoomTool)

    result = await actions.run_generate_storyboard("slug", "a red cube")
    assert "refused" in result and "RAM never cleared" in result
    assert called == []   # tool never even constructed — the RAM check short-circuits first


def test_storyboard_uses_the_lighter_default_ram_threshold(monkeypatch):
    """Kevin, 2026-07-28 (round two): 'It seems like the model is not even
    loading into RAM' — traced to ram_gate's 2GB default being far too
    low for the ~10GB LTX clip model (enable_sequential_cpu_offload keeps
    the WHOLE model resident), so the gate said "safe" while 5.5GB was
    free and the load then silently swap-thrashed for minutes with zero
    feedback. Storyboard (a much smaller image model) keeps the ordinary
    default — only the clip/advance paths need the raised floor."""
    calls = []
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: calls.append(kw) or (True, ""))
    from sovereign_agent.tools.base import ToolResult

    class _FakeTool:
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
            self.Args = _A
        async def execute(self, args, *, trace_id):
            return ToolResult(ok=True, output={"path": "/fake/storyboard.png"})

    import sovereign_agent.tools.generate_storyboard_image as real_mod
    monkeypatch.setattr(real_mod, "GenerateStoryboardImageTool", _FakeTool)

    import asyncio
    asyncio.run(actions.run_generate_storyboard("slug", "a red cube"))
    assert "min_available_mb" not in calls[0]  # ram_gate's own lighter default applies


@pytest.mark.asyncio
async def test_run_generate_clip_success_message(monkeypatch, tmp_path):
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))

    from sovereign_agent.tools.base import ToolResult

    class _FakeTool:
        Args = None
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
            self.Args = _A
        async def execute(self, args, *, trace_id, on_step=None):
            return ToolResult(ok=True, output={"path": "/fake/clip.mp4"})

    import sovereign_agent.tools.generate_movie_clip as real_mod
    monkeypatch.setattr(real_mod, "GenerateMovieClipTool", _FakeTool)

    result = await actions.run_generate_clip("slug", "a red cube")
    assert "clip generated" in result and "/fake/clip.mp4" in result


@pytest.mark.asyncio
async def test_run_generate_clip_requires_the_realistic_ram_floor(monkeypatch):
    calls = []
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: calls.append(kw) or (True, ""))
    from sovereign_agent.tools.base import ToolResult

    class _FakeTool:
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
            self.Args = _A
        async def execute(self, args, *, trace_id, on_step=None):
            return ToolResult(ok=True, output={"path": "/fake/clip.mp4"})

    import sovereign_agent.tools.generate_movie_clip as real_mod
    monkeypatch.setattr(real_mod, "GenerateMovieClipTool", _FakeTool)

    await actions.run_generate_clip("slug", "a red cube")
    assert calls[0]["min_available_mb"] == actions.CLIP_MIN_AVAILABLE_MB


@pytest.mark.asyncio
async def test_run_generate_clip_threads_on_step_through_to_the_tool(monkeypatch):
    """Kevin, 2026-07-28: 'can we watch the movies generate live???' —
    confirms on_step actually reaches the tool's execute() call, not just
    that passing it doesn't crash."""
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))
    from sovereign_agent.tools.base import ToolResult

    received = {}

    class _FakeTool:
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
            self.Args = _A
        async def execute(self, args, *, trace_id, on_step=None):
            received["on_step"] = on_step
            if on_step is not None:
                on_step(3, 30)   # simulate one real diffusers step callback
            return ToolResult(ok=True, output={"path": "/fake/clip.mp4"})

    import sovereign_agent.tools.generate_movie_clip as real_mod
    monkeypatch.setattr(real_mod, "GenerateMovieClipTool", _FakeTool)

    seen_steps = []
    await actions.run_generate_clip("slug", "a red cube", on_step=lambda s, t: seen_steps.append((s, t)))
    assert received["on_step"] is not None
    assert seen_steps == [(3, 30)]


@pytest.mark.asyncio
async def test_run_generate_clip_tool_failure_message(monkeypatch):
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))
    from sovereign_agent.tools.base import ToolResult

    class _FakeTool:
        def __init__(self, data_dir=None):
            from pydantic import BaseModel
            class _A(BaseModel):
                project_slug: str
                prompt: str
            self.Args = _A
        async def execute(self, args, *, trace_id, on_step=None):
            return ToolResult(ok=False, error="insufficient_vram: boom")

    import sovereign_agent.tools.generate_movie_clip as real_mod
    monkeypatch.setattr(real_mod, "GenerateMovieClipTool", _FakeTool)

    result = await actions.run_generate_clip("slug", "a red cube")
    assert "clip failed" in result and "insufficient_vram" in result


# ── pitches (no RAM gate) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_draft_pitches_never_calls_ram_gate(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: called.append(1) or (True, ""))

    class _FakePlanResult:
        goal = "g"; steps = ["s1", "s2"]; output_path = str(tmp_path / "out.md"); notes = ""

    class _FakePlanner:
        def plan(self, **kw):
            return _FakePlanResult()

    import sovereign_agent.planners as planners_mod
    monkeypatch.setattr(planners_mod, "get_planner", lambda name: _FakePlanner())

    class _FakeContStore:
        def __init__(self, *a, **kw): pass
        def create(self, **kw): pass

    import sovereign_agent.continuation as cont_mod
    monkeypatch.setattr(cont_mod, "ContinuationStore", _FakeContStore)

    result = await actions.run_draft_pitches("hopeful futures")
    assert "queued 2 pitch" in result
    assert called == []   # RAM gate never touched


# ── episode lifecycle (real filesystem) ────────────────────────────────────


def _store(tmp_path) -> EpisodeStore:
    return EpisodeStore(tmp_path / "movie_episodes", tmp_path / "movies_work")


@pytest.mark.asyncio
async def test_run_start_episode_without_project_or_series_is_honest(tmp_path):
    result = await actions.run_start_episode("no-such-slug", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "cannot start episode" in result


@pytest.mark.asyncio
async def test_run_start_episode_auto_creates_series_from_movie_project(tmp_path):
    save_project(MovieProject(title="Neon Skyline", genre="short-film", style="animated",
                              logline="a city that dreams back"), tmp_path)

    result = await actions.run_start_episode("neon-skyline", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "started episode ep-neon-skyline" in result

    series = load_series_by_slug("neon-skyline", tmp_path)
    assert series is not None
    assert series.logline == "a city that dreams back"
    assert len(series.season_ids) == 1


@pytest.mark.asyncio
async def test_run_start_episode_reuses_latest_season_on_second_call(tmp_path):
    save_project(MovieProject(title="Neon Skyline"), tmp_path)
    r1 = await actions.run_start_episode("neon-skyline", data_dir=tmp_path, sandbox_dir=tmp_path)
    r2 = await actions.run_start_episode("neon-skyline", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "started episode ep-neon-skyline-s01-e01" in r1
    assert "started episode ep-neon-skyline-s01-e02" in r2

    series = load_series_by_slug("neon-skyline", tmp_path)
    assert len(series.season_ids) == 1   # still just one season


@pytest.mark.asyncio
async def test_run_start_episode_seeds_a_real_shot_with_the_given_beat(tmp_path):
    """Kevin, 2026-07-28: 'I clicked run 5 clips. How do I know if that is
    working? I see no obvious observables' — root cause was episodes
    starting with ZERO shots, so Advance always completed instantly. This
    is the fix under direct test: Start Episode must leave behind a real,
    pending ShotEntry."""
    save_project(MovieProject(title="Neon Skyline", logline="a city that dreams back"), tmp_path)
    result = await actions.run_start_episode(
        "neon-skyline", beat="a lone drone crosses the skyline at dawn",
        data_dir=tmp_path, sandbox_dir=tmp_path,
    )
    assert "shot 1 queued" in result
    assert "a lone drone crosses the skyline at dawn" in result

    store = _store(tmp_path)
    ep_id = result.split("started episode ")[1].split(" (")[0]
    ep = store.get(ep_id)
    assert len(ep.shots) == 1
    assert ep.shots[0].status == "pending"
    assert ep.shots[0].beat == "a lone drone crosses the skyline at dawn"
    assert ep.shots[0].target_clips == actions.DEFAULT_TARGET_CLIPS


@pytest.mark.asyncio
async def test_run_start_episode_falls_back_to_series_logline_when_beat_is_blank(tmp_path):
    save_project(MovieProject(title="Neon Skyline", logline="a city that dreams back"), tmp_path)
    result = await actions.run_start_episode("neon-skyline", data_dir=tmp_path, sandbox_dir=tmp_path)
    ep_id = result.split("started episode ")[1].split(" (")[0]
    ep = _store(tmp_path).get(ep_id)
    assert ep.shots[0].beat == "a city that dreams back"


@pytest.mark.asyncio
async def test_run_add_shot_queues_another_shot_on_an_existing_episode(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.shots.append(ShotEntry(shot_number=1, beat="first", target_clips=1))
    store.save(ep)

    result = await actions.run_add_shot(ep.episode_id, "a second beat", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "queued shot 2" in result

    ep = store.get(ep.episode_id)
    assert len(ep.shots) == 2
    assert ep.shots[1].beat == "a second beat"
    assert ep.shots[1].status == "pending"


@pytest.mark.asyncio
async def test_run_add_shot_refuses_blank_beat(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    result = await actions.run_add_shot(ep.episode_id, "   ", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "refused" in result
    assert len(store.get(ep.episode_id).shots) == 0


@pytest.mark.asyncio
async def test_run_add_shot_refuses_on_a_terminal_episode(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.status = "completed"
    store.save(ep)
    result = await actions.run_add_shot(ep.episode_id, "too late", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "refused" in result and "completed" in result


@pytest.mark.asyncio
async def test_run_advance_episode_ram_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (False, "still tight"))
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    result = await actions.run_advance_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "advance refused" in result and "still tight" in result


@pytest.mark.asyncio
async def test_run_advance_episode_requires_the_realistic_ram_floor(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: calls.append(kw) or (True, ""))
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    await actions.run_advance_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert calls[0]["min_available_mb"] == actions.CLIP_MIN_AVAILABLE_MB


@pytest.mark.asyncio
async def test_run_advance_episode_no_shots_fails_health_check(monkeypatch, tmp_path):
    """Kevin, 2026-07-29: 'add a episode verify health and success auto
    checking feature.' A zero-shot episode never did any real work — it
    must not be able to call itself completed."""
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    result = await actions.run_advance_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "episode_failed_health_check" in result


@pytest.mark.asyncio
async def test_run_advance_episode_threads_on_step_through_to_the_runner(monkeypatch, tmp_path):
    """Kevin, 2026-07-28: 'can we watch the movies generate live???' —
    confirms on_step reaches movie_episode_render_runner.advance_episode
    and, through it, the real generate_clip_async call."""
    monkeypatch.setattr(ram_gate, "wait_for_ram_safe", lambda **kw: (True, ""))

    import sovereign_agent.movie_episode_render_runner as runner_mod
    received = {}

    async def fake_generate_clip_async(*, prompt, negative_prompt, out_path,
                                        condition_image_path=None, on_step=None, **_):
        received["on_step"] = on_step
        if on_step is not None:
            on_step(1, 30)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
    monkeypatch.setattr(runner_mod, "generate_clip_async", fake_generate_clip_async)
    monkeypatch.setattr(runner_mod, "extract_last_frame", lambda *a, **kw: type(
        "R", (), {"ok": False, "path": None, "detail": "stub"})())

    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    from sovereign_agent.movie_episode_render import ShotEntry
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=1))
    store.save(ep)

    seen_steps = []
    await actions.run_advance_episode(
        ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path,
        on_step=lambda s, t: seen_steps.append((s, t)),
    )
    assert received["on_step"] is not None
    assert seen_steps == [(1, 30)]


@pytest.mark.asyncio
async def test_run_pause_and_resume_episode(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")

    r1 = await actions.run_pause_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "paused" in r1
    assert store.get(ep.episode_id).status == "paused"

    r2 = await actions.run_resume_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "resumed" in r2
    assert store.get(ep.episode_id).status == "active"


@pytest.mark.asyncio
async def test_run_resume_restarts_any_poisoned_shot(tmp_path):
    """Kevin, 2026-07-29: "make it restart instead of resume then." A
    poisoned shot never fixes itself — un-pausing alone used to leave it
    poisoned, and the next advance call would falsely declare the whole
    episode "completed" (the bug just fixed in
    movie_episode_render_runner.advance_episode). Resume must reset the
    poisoned shot back to pending so there's real work queued again."""
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.status = "paused"
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=1,
                              status="poisoned", consecutive_failures=3))
    ep.shots.append(ShotEntry(shot_number=2, beat="c", target_clips=1, status="done"))
    store.save(ep)

    result = await actions.run_resume_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "restarting shot(s) [1]" in result

    reloaded = store.get(ep.episode_id)
    assert reloaded.status == "active"
    assert reloaded.shots[0].status == "pending"
    assert reloaded.shots[0].consecutive_failures == 0
    assert reloaded.shots[1].status == "done"   # untouched — it actually finished


@pytest.mark.asyncio
async def test_run_resume_with_no_poisoned_shot_keeps_the_plain_message(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.status = "paused"
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=1, status="pending"))
    store.save(ep)

    result = await actions.run_resume_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert result == f"episode {ep.episode_id} resumed"
    assert store.get(ep.episode_id).shots[0].status == "pending"


@pytest.mark.asyncio
async def test_run_pause_terminal_episode_is_a_no_op_message(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    with store.lock(ep.episode_id) as locked:
        locked.status = "completed"

    result = await actions.run_pause_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "already completed" in result
    assert store.get(ep.episode_id).status == "completed"


@pytest.mark.asyncio
async def test_run_resume_non_paused_episode_is_a_no_op_message(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    result = await actions.run_resume_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "not paused" in result


# ── verify episode health (Kevin, 2026-07-29: "add a episode verify
# health and success auto checking feature") ───────────────────────────────


@pytest.mark.asyncio
async def test_run_verify_episode_health_reports_a_poisoned_shot(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=1, status="poisoned"))
    store.save(ep)

    result = await actions.run_verify_episode_health(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "FAILED" in result
    assert "poisoned" in result


@pytest.mark.asyncio
async def test_run_verify_episode_health_on_a_missing_episode(tmp_path):
    result = await actions.run_verify_episode_health("no-such-episode", data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "verify failed" in result


# ── assembly (real ffmpeg, mirrors test_assemble_movie_episode.py) ─────────


pytestmark_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_run_assemble_episode_produces_a_real_file(tmp_path):
    store = _store(tmp_path)
    ep = store.create(series_slug="s", season_id="s-s01", episode_number=1, title="T")
    clip = tmp_path / "clip1.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=8",
         "-frames:v", "8", str(clip)],
        capture_output=True, timeout=30, check=True,
    )
    ep.shots.append(ShotEntry(shot_number=1, beat="b", target_clips=1,
                               clips=[ClipEntry(clip_number=1, path=str(clip), quality_status="pass")],
                               status="done"))
    ep.status = "completed"
    store.save(ep)

    result = await actions.run_assemble_episode(ep.episode_id, data_dir=tmp_path, sandbox_dir=tmp_path)
    assert "Assembled 1 clips" in result
