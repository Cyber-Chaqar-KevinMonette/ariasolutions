"""movie_generation_actions — the one place that calls RAM-gate + a real
movie-production action + returns a status string.

movie-focus-d (Kevin, 2026-07-28): the split-pane quick-action surface
(`movie_pane.py`) and the full Movie Studio modal (`movie_studio_screen.py`)
both need to trigger the same real generation/render calls. Rather than
each UI wiring the GPU calls itself (duplicated, and only one of them
would get the RAM-safety wait), every real action lives here ONCE; both
UIs call these functions and just render the returned string + drive their
own `on_wait` callback to a status widget.

Every GPU-heavy action (storyboard, clip, episode-advance) is gated by
`ram_gate.wait_for_ram_safe()` first — Kevin: "don't rush into the gpu too
fast when switching modes." `run_draft_pitches`/`run_pause_episode`/
`run_resume_episode` are NOT gated — they don't touch the GPU (pitches are
local-LLM planning + a continuation record; pause/resume just flip a
status flag on disk).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from sovereign_agent import ram_gate

__all__ = [
    "run_generate_storyboard",
    "run_generate_clip",
    "run_draft_pitches",
    "run_start_episode",
    "run_add_shot",
    "run_advance_episode",
    "run_pause_episode",
    "run_resume_episode",
    "run_verify_episode_health",
    "run_assemble_episode",
]

# Kevin, 2026-07-28: "I clicked run 5 clips. How do I know if that is
# working? I see no obvious observables." Root cause traced live: episodes
# started with ZERO shots (nothing anywhere ever appended a ShotEntry), so
# advance_episode()'s shot-selection always found None immediately and
# completed the episode instantly — no RAM wait, no GPU call, no step
# progress. DEFAULT_TARGET_CLIPS matches movie_pane.py's RUN_BATCH_SIZE so
# "Run (5 clips)" naturally corresponds to filling one shot's worth of work.
DEFAULT_TARGET_CLIPS = 5

# Kevin, 2026-07-28 (round two): "It seems like the model is not even
# loading into RAM." Root cause traced live: ram_gate's DEFAULT_MIN_AVAILABLE_MB
# (2048MB) was reasoned around "don't OOM-crash, swap absorbs the rest" —
# it never accounted for how LONG that absorption takes. movie_clip_generation's
# own docstring already documents the real footprint: enable_sequential_cpu_offload()
# keeps the WHOLE ~10GB LTX pipeline resident in system RAM by design. With
# only 2GB required as headroom, the gate says "safe" the moment 2GB is
# free even though 8+ of that 10GB then has to swap to disk during
# from_pretrained() — before a single denoising step (and thus before
# on_step's first callback) runs. That multi-minute, fully-silent swap-in
# is indistinguishable from "nothing is happening." Confirmed live: this
# machine had ~4.5-5.5GB available (heavy Firefox/Playwright RAM use) at
# the exact moment this was reported — nowhere near the model's real size.
# CLIP_MIN_AVAILABLE_MB requires real headroom for the whole resident
# model (10GB) plus a safety margin, so the gate now honestly REFUSES with
# a clear "not enough RAM" reason instead of silently proceeding into an
# unobservable swap-thrash. Storyboard generation (a much smaller image
# model) keeps ram_gate's own lighter default.
CLIP_MIN_AVAILABLE_MB = 11264

OnWait = Optional[Callable[[Optional[int], float], None]]
OnStep = Optional[Callable[[int, int], None]]


def _emit(flag: str, *, trace_id: str, **payload) -> None:
    """Best-effort observability event. Kevin, 2026-07-28: 'I am not
    getting anything on the observability side' — NONE of these actions
    wrote to events.jsonl before this, which is what the cockpit's
    live-pane/observability strips actually tail. A tool succeeding
    silently (from this module's own return string) is invisible to
    that whole surface unless something calls emit_event() explicitly —
    dream_runner.py already does this for dream cycles; this mirrors it.
    Never raises — a broken event write must never break the real action."""
    try:
        from sovereign_agent.events import emit_event
        emit_event(flag, plane="movie", trace_id=trace_id, payload=payload)
    except Exception:  # noqa: BLE001
        pass


def _wrap_on_step_for_events(on_step: OnStep, *, trace_id: str, every: int = 5) -> OnStep:
    """Ticks emit_event every `every` steps (not every single one — 30
    events per clip would flood the live pane) alongside the caller's own
    on_step, so real generation progress is visible in observability too,
    not just the pane's own status line."""
    def _combined(step: int, total: int) -> None:
        if step == 1 or step == total or step % every == 0:
            _emit("movie-clip-step-d", trace_id=trace_id, step=step, total_steps=total)
        if on_step is not None:
            on_step(step, total)
    return _combined


def _resolve_dirs(data_dir: Optional[Path], sandbox_dir: Optional[Path]) -> tuple[Path, Path]:
    if data_dir is None or sandbox_dir is None:
        from sovereign_agent.config import SETTINGS
        if data_dir is None:
            data_dir = SETTINGS.paths.data_dir
        if sandbox_dir is None:
            sandbox_dir = SETTINGS.paths.sandbox_dir
    return Path(data_dir), Path(sandbox_dir)


def _episode_store(data_dir: Path, sandbox_dir: Path):
    from sovereign_agent.movie_episode_render import EpisodeStore
    return EpisodeStore(data_dir / "movie_episodes", sandbox_dir / "movies")


def _safety_level_for_series(series_slug: str, data_dir: Path) -> str:
    """Kevin, 2026-07-29: 'add movie production guardrails... add safety
    levels. Which can be applied per series.' No series yet (a brand new
    project that hasn't been promoted to a Series by run_start_episode
    yet) degrades to the strict default — never a permissive fallback."""
    from sovereign_agent.movie_content_safety import DEFAULT_SAFETY_LEVEL
    from sovereign_agent.movie_series import load_series_by_slug
    series = load_series_by_slug(series_slug, data_dir)
    return series.safety_level if series is not None else DEFAULT_SAFETY_LEVEL


# ── Single-shot quick actions (mirror movie_studio_screen.py's own calls) ──


async def run_generate_storyboard(
    project_slug: str, prompt: str, *, on_wait: OnWait = None, data_dir: Optional[Path] = None,
) -> str:
    trace_id = f"movie:{project_slug}"
    _emit("movie-storyboard-start-d", trace_id=trace_id, project_slug=project_slug, prompt=prompt)

    resolved_data_dir, _ = _resolve_dirs(data_dir, None)
    from sovereign_agent.movie_content_safety import assess_prompt_safety
    safety_level = _safety_level_for_series(project_slug, resolved_data_dir)
    verdict = assess_prompt_safety(prompt, safety_level)
    if not verdict.allowed:
        _emit("movie-storyboard-x", trace_id=trace_id, reason=verdict.reason)
        return f"storyboard refused: {verdict.reason}"

    ok, reason = ram_gate.wait_for_ram_safe(on_wait=on_wait)
    if not ok:
        _emit("movie-storyboard-x", trace_id=trace_id, reason=reason)
        return f"storyboard refused: {reason}"

    from sovereign_agent.tools.generate_storyboard_image import GenerateStoryboardImageTool

    tool = GenerateStoryboardImageTool(data_dir)
    result = await tool.execute(
        tool.Args(project_slug=project_slug, prompt=prompt), trace_id="movie-generation-actions"
    )
    if not result.ok:
        _emit("movie-storyboard-x", trace_id=trace_id, error=result.error)
        return f"storyboard failed: {result.error}"
    _emit("movie-storyboard-end-d", trace_id=trace_id, path=result.output["path"])
    return f"storyboard generated → {result.output['path']}"


async def run_generate_clip(
    project_slug: str, prompt: str, *, on_wait: OnWait = None,
    on_step: OnStep = None, data_dir: Optional[Path] = None,
) -> str:
    """on_step(step, total_steps) — real per-denoising-step progress
    (Kevin, 2026-07-28: "can we watch the movies generate live???"),
    confirmed real via diffusers' callback_on_step_end. Fires from the GPU
    thread; the caller (movie_pane.py) hops back to the UI thread itself."""
    trace_id = f"movie:{project_slug}"
    _emit("movie-clip-start-d", trace_id=trace_id, project_slug=project_slug, prompt=prompt)

    resolved_data_dir, _ = _resolve_dirs(data_dir, None)
    from sovereign_agent.movie_content_safety import assess_prompt_safety, augment_negative_prompt
    safety_level = _safety_level_for_series(project_slug, resolved_data_dir)
    verdict = assess_prompt_safety(prompt, safety_level)
    if not verdict.allowed:
        _emit("movie-clip-x", trace_id=trace_id, reason=verdict.reason)
        return f"clip refused: {verdict.reason}"

    ok, reason = ram_gate.wait_for_ram_safe(on_wait=on_wait, min_available_mb=CLIP_MIN_AVAILABLE_MB)
    if not ok:
        _emit("movie-clip-x", trace_id=trace_id, reason=reason)
        return f"clip refused: {reason}"

    from sovereign_agent.tools.generate_movie_clip import GenerateMovieClipTool

    tool = GenerateMovieClipTool(data_dir)
    negative_prompt = augment_negative_prompt(
        "worst quality, inconsistent motion, blurry, jittery, distorted", safety_level,
    )
    result = await tool.execute(
        tool.Args(project_slug=project_slug, prompt=prompt, negative_prompt=negative_prompt),
        trace_id="movie-generation-actions",
        on_step=_wrap_on_step_for_events(on_step, trace_id=trace_id),
    )
    if not result.ok:
        _emit("movie-clip-x", trace_id=trace_id, error=result.error)
        return f"clip failed: {result.error}"
    _emit("movie-clip-end-d", trace_id=trace_id, path=result.output["path"])
    return f"clip generated → {result.output['path']}"


async def run_draft_pitches(theme: str, *, data_dir: Optional[Path] = None) -> str:
    """No RAM gate — local-LLM planning + a continuation record, not a
    GPU vision-model load. Same logic movie_studio_screen.py's
    _draft_pitches_current already ran inline, extracted verbatim."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.continuation import ContinuationStore
    from sovereign_agent.planners import get_planner
    from sovereign_agent.planners.base import PlannerError

    if data_dir is None:
        data_dir = SETTINGS.paths.data_dir

    trace_id = f"movie-pitch:{theme or '(open theme)'}"
    _emit("movie-pitch-start-d", trace_id=trace_id, theme=theme)

    import time
    output = SETTINGS.paths.sandbox_dir / "movie_pitches" / f"pitches-{int(time.time())}.md"
    output.parent.mkdir(parents=True, exist_ok=True)

    planner = get_planner("movie-pitch")
    plan_kwargs: dict = {"output": str(output)}
    if theme:
        plan_kwargs["theme"] = theme
    try:
        result = planner.plan(**plan_kwargs)
    except PlannerError as exc:
        _emit("movie-pitch-x", trace_id=trace_id, error=str(exc))
        return f"pitch planning failed: {exc}"

    try:
        store = ContinuationStore(SETTINGS.paths.continuations_dir)
        store.create(
            goal=result.goal, planner="movie-pitch", planner_args=plan_kwargs,
            steps=result.steps, output_path=result.output_path, notes=result.notes,
        )
    except Exception as exc:  # noqa: BLE001
        _emit("movie-pitch-x", trace_id=trace_id, error=str(exc))
        return f"couldn't queue pitch continuation: {type(exc).__name__}: {exc}"

    _emit("movie-pitch-end-d", trace_id=trace_id, output=str(output), count=len(result.steps))
    return (f"queued {len(result.steps)} pitch(es) → {output} "
            "— drain the continuation to generate real content")


# ── Episode-production controls ────────────────────────────────────────────


async def run_start_episode(
    series_slug: str, *, title: str = "", beat: str = "",
    target_clips: int = DEFAULT_TARGET_CLIPS, on_wait: OnWait = None,
    data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    """Auto-creates the Series (seeded from the matching movie project, if
    one exists and no Series exists yet) and the next season if needed,
    then a fresh episode in it. Sets the new episode focus. Kevin's own
    scope call: no full series/season picker UI yet — this always extends
    whatever's focused, one episode at a time.

    Real bug found + fixed here (Kevin, 2026-07-28: "I clicked run 5 clips.
    How do I know if that is working? I see no obvious observables"):
    this function used to create the episode with an EMPTY shot list —
    advance_episode()'s shot-selection always found None immediately and
    marked the episode "completed" with zero RAM-gate waits, zero GPU
    calls, zero step-progress ticks. Now it always seeds shot 1 with a
    real beat (the caller's own text, falling back to the series logline,
    then a generic default — never left blank) so Advance/Run actually
    have something to render."""
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{series_slug}"
    _emit("movie-episode-start-d", trace_id=trace_id, series_slug=series_slug)

    from sovereign_agent import movie_series

    series = movie_series.load_series_by_slug(series_slug, data_dir)
    if series is None:
        from sovereign_agent.movie_projects import load_by_slug as load_project_by_slug
        project = load_project_by_slug(series_slug, data_dir)
        if project is None:
            _emit("movie-episode-x", trace_id=trace_id, reason="no project or series found")
            return (f"cannot start episode: no movie project or series with slug "
                    f"{series_slug!r} — define a movie project first")
        movie_series.save_series(movie_series.Series(
            title=project.title, logline=project.logline,
            genre=project.genre, style=project.style,
        ), data_dir)
        series = movie_series.load_series_by_slug(series_slug, data_dir)

    if not series.season_ids:
        season = movie_series.create_season(series_slug, "Season One", data_dir)
    else:
        season = movie_series.load_season(series.season_ids[-1], data_dir)
        if season is None:
            season = movie_series.create_season(series_slug, "Season One", data_dir)

    shot_beat = beat.strip() or series.logline.strip() or f"{series.title}, opening shot"

    # Kevin, 2026-07-29: "add movie production guardrails... add safety
    # levels. Which can be applied per series." Checked BEFORE creating
    # the episode — a refused beat should never leave an orphaned empty
    # episode behind.
    from sovereign_agent.movie_content_safety import assess_prompt_safety
    verdict = assess_prompt_safety(shot_beat, series.safety_level)
    if not verdict.allowed:
        _emit("movie-episode-x", trace_id=trace_id, reason=verdict.reason)
        return f"cannot start episode: {verdict.reason}"

    episode_number = len(season.episode_ids) + 1
    store = _episode_store(data_dir, sandbox_dir)
    episode = store.create(
        series_slug=series_slug, season_id=season.season_id, episode_number=episode_number,
        title=title or f"{series.title} — Episode {episode_number}",
    )

    from sovereign_agent.movie_episode_render import ShotEntry

    episode.shots.append(ShotEntry(shot_number=1, beat=shot_beat, target_clips=max(1, target_clips)))
    store.save(episode)

    movie_series.add_episode_to_season(season.season_id, episode.episode_id, data_dir)
    movie_series.set_episode_focus(
        episode.episode_id, "started a new episode from the movie pane", data_dir,
    )
    _emit("movie-episode-end-d", trace_id=trace_id, episode_id=episode.episode_id, shot_beat=shot_beat)
    return (f"started episode {episode.episode_id} ({episode.title}) — shot 1 queued "
            f"({target_clips} clips: {shot_beat!r}) — ready to Advance")


async def run_add_shot(
    episode_id: str, beat: str, *, target_clips: int = DEFAULT_TARGET_CLIPS,
    data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    """Queues another shot into an already-started episode — the follow-up
    half of the run_start_episode fix: a real multi-shot episode needs a
    way to add MORE work after the first shot is done, not just at Start."""
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{episode_id}"
    beat = beat.strip()
    if not beat:
        return "add shot refused: needs a beat/description for the shot"

    from sovereign_agent.movie_content_safety import assess_prompt_safety
    from sovereign_agent.movie_episode_render import ShotEntry

    store = _episode_store(data_dir, sandbox_dir)
    try:
        with store.lock(episode_id) as ep:
            if ep.is_terminal():
                _emit("movie-episode-x", trace_id=trace_id, action="add_shot",
                      reason=f"episode is {ep.status}")
                return f"add shot refused: episode {episode_id} is {ep.status}"
            # Kevin, 2026-07-29: "add movie production guardrails... add
            # safety levels. Which can be applied per series." A shot
            # added mid-episode gets the SAME check as the opening one.
            safety_level = _safety_level_for_series(ep.series_slug, data_dir)
            verdict = assess_prompt_safety(beat, safety_level)
            if not verdict.allowed:
                _emit("movie-episode-x", trace_id=trace_id, action="add_shot", reason=verdict.reason)
                return f"add shot refused: {verdict.reason}"
            shot_number = len(ep.shots) + 1
            ep.shots.append(ShotEntry(shot_number=shot_number, beat=beat, target_clips=max(1, target_clips)))
    except Exception as exc:  # noqa: BLE001
        _emit("movie-episode-x", trace_id=trace_id, action="add_shot", error=f"{type(exc).__name__}: {exc}")
        return f"add shot failed: {type(exc).__name__}: {exc}"
    _emit("movie-episode-shot-added-d", trace_id=trace_id, shot_number=shot_number, beat=beat)
    return f"queued shot {shot_number} ({target_clips} clips: {beat!r}) on episode {episode_id}"


async def run_advance_episode(
    episode_id: str, *, on_wait: OnWait = None, on_step: OnStep = None,
    data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    """One clip attempt via movie_episode_render_runner.advance_episode —
    the already-proven-live chaining mechanism. on_step(step, total_steps)
    is real per-denoising-step progress (Kevin, 2026-07-28: "can we watch
    the movies generate live???").

    Real bug found writing this (2026-07-28): advance_episode() is a SYNC
    function that internally calls asyncio.run(generate_clip_async(...))
    — fine when called from a plain sync context (CLI, direct tests), but
    calling it directly from HERE (an async function, always awaited from
    inside a running loop) raised "asyncio.run() cannot be called from a
    running event loop" the moment a real shot existed to advance — i.e.
    the exact path Kevin's Advance/Run buttons take once past the empty-
    episode case. asyncio.to_thread() runs it in a fresh thread with no
    pre-existing loop, same fix shape as Textual's own @work(thread=True)."""
    import asyncio
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{episode_id}"
    _emit("movie-advance-start-d", trace_id=trace_id, episode_id=episode_id)

    ok, reason = ram_gate.wait_for_ram_safe(on_wait=on_wait, min_available_mb=CLIP_MIN_AVAILABLE_MB)
    if not ok:
        _emit("movie-advance-x", trace_id=trace_id, reason=reason)
        return f"advance refused: {reason}"

    from sovereign_agent.movie_episode_render_runner import advance_episode

    store = _episode_store(data_dir, sandbox_dir)
    try:
        result = await asyncio.to_thread(
            advance_episode, episode_id=episode_id, store=store, data_dir=data_dir,
            on_step=_wrap_on_step_for_events(on_step, trace_id=trace_id),
        )
    except Exception as exc:  # noqa: BLE001
        _emit("movie-advance-x", trace_id=trace_id, error=f"{type(exc).__name__}: {exc}")
        return f"advance failed: {type(exc).__name__}: {exc}"

    parts = [result.step_outcome]
    if result.shot_number >= 0:
        parts.append(f"shot {result.shot_number} clip {result.clip_number}")
    parts.append(f"episode: {result.episode_status}")
    if result.reason:
        parts.append(result.reason)
    _emit("movie-advance-end-d", trace_id=trace_id, step_outcome=result.step_outcome,
          episode_status=result.episode_status)
    return " — ".join(parts)


async def run_pause_episode(
    episode_id: str, *, data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{episode_id}"
    store = _episode_store(data_dir, sandbox_dir)
    try:
        with store.lock(episode_id) as ep:
            if ep.is_terminal():
                return f"episode {episode_id} is already {ep.status} — nothing to pause"
            ep.status = "paused"
    except Exception as exc:  # noqa: BLE001
        _emit("movie-episode-x", trace_id=trace_id, action="pause", error=f"{type(exc).__name__}: {exc}")
        return f"pause failed: {type(exc).__name__}: {exc}"
    _emit("movie-episode-pause-d", trace_id=trace_id)
    return f"episode {episode_id} paused"


async def run_resume_episode(
    episode_id: str, *, data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    """Kevin, 2026-07-29: "make it restart instead of resume then." Real
    bug this fixes: un-pausing alone used to be useless once a shot was
    poisoned — advance_episode()'s shot-picker can't see poisoned shots,
    so the very next advance call just declared the episode falsely
    "completed" (confirmed live: an episode whose only shot failed every
    retry with a real torch/import error still reported "completed
    successfully" with zero clips ever rendered, the moment it got
    resumed). A poisoned shot never fixes itself, so Resume now also
    resets any poisoned shot(s) back to pending with a fresh retry count
    — this is what "resume" should have meant all along."""
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{episode_id}"
    store = _episode_store(data_dir, sandbox_dir)
    restarted_shots: list[int] = []
    try:
        with store.lock(episode_id) as ep:
            if ep.status != "paused":
                return f"episode {episode_id} is {ep.status}, not paused — nothing to resume"
            ep.status = "active"
            for shot in ep.shots:
                if shot.status == "poisoned":
                    shot.status = "pending"
                    shot.consecutive_failures = 0
                    restarted_shots.append(shot.shot_number)
    except Exception as exc:  # noqa: BLE001
        _emit("movie-episode-x", trace_id=trace_id, action="resume", error=f"{type(exc).__name__}: {exc}")
        return f"resume failed: {type(exc).__name__}: {exc}"
    _emit("movie-episode-resume-d", trace_id=trace_id, restarted_shots=restarted_shots)
    if restarted_shots:
        return f"episode {episode_id} resumed — restarting shot(s) {restarted_shots}"
    return f"episode {episode_id} resumed"


async def run_verify_episode_health(
    episode_id: str, *, data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    """Kevin, 2026-07-29: "add a episode verify health and success auto
    checking feature after every episode." advance_episode() now runs
    this automatically before it will ever call an episode "completed" —
    this is the same check exposed standalone, for re-verifying any
    episode on demand (including old ones from before this feature
    existed, or ones you just want to double-check). No RAM/GPU gate —
    this is a fast, local filesystem + ffprobe check, not a model call."""
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{episode_id}"
    store = _episode_store(data_dir, sandbox_dir)
    try:
        episode = store.get(episode_id)
    except Exception as exc:  # noqa: BLE001
        _emit("movie-episode-x", trace_id=trace_id, action="verify", error=f"{type(exc).__name__}: {exc}")
        return f"verify failed: {type(exc).__name__}: {exc}"

    from sovereign_agent.movie_episode_health import verify_episode_health
    report = verify_episode_health(episode)
    _emit("movie-episode-health-d" if report.healthy else "movie-episode-health-x",
          trace_id=trace_id, healthy=report.healthy, issues=len(report.issues))
    return report.summary()


async def run_assemble_episode(
    episode_id: str, *, allow_partial: bool = False,
    data_dir: Optional[Path] = None, sandbox_dir: Optional[Path] = None,
) -> str:
    data_dir, sandbox_dir = _resolve_dirs(data_dir, sandbox_dir)
    trace_id = f"movie-episode:{episode_id}"
    _emit("movie-assemble-start-d", trace_id=trace_id, episode_id=episode_id)

    from sovereign_agent.tools.assemble_movie_episode import AssembleMovieEpisodeTool

    tool = AssembleMovieEpisodeTool(data_dir=data_dir, work_root=sandbox_dir / "movies")
    result = await tool.execute(
        tool.Args(episode_id=episode_id, allow_partial=allow_partial),
        trace_id="movie-generation-actions",
    )
    if not result.ok:
        _emit("movie-assemble-x", trace_id=trace_id, error=result.error)
        return f"assembly failed: {result.error}"
    _emit("movie-assemble-end-d", trace_id=trace_id, path=result.output.get("path"))
    return result.output["message"]
