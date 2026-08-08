"""movie_auto_series_runner.py — the bounded, unattended "Auto Series" loop.

Kevin, 2026-07-28: "the entire system has to manage and create an entire
series. No human required... use graceful sleep schedules to let the
system find a healthy state to load the video gen model. So unload,
sleep/wait, load movie gen model -- picks up content."

Mirrors `self_practice.py`/`dream_runner.py`'s bounded, injectable loop
shape exactly. The ONLY things that stop this loop:
  1. The `AutoCrownStore` session it's running under expires or is
     cancelled — the SAME human-armed, timed, tier-capped consent
     mechanism every other unattended loop in this repo already uses
     (never a separate, ungated "run forever" mechanism).
  2. `should_stop()` — the caller's own cancel flag (movie_pane.py's busy
     guard, flipped by a "Stop Auto Series" button).
  3. Real, unrecoverable episode/series terminal states.

Never an arbitrary CLIP or EPISODE count cap — the whole point is "runs
for as long as the human already said is okay," not a hardcoded number.
`shots_per_episode` IS a real, deliberate bound (default 3) — without
capping how many shots a single episode can grow to, the loop would
preemptively queue "one more shot" forever and an episode would never
reach a real terminal state, so a new episode (the actual "whole series"
part) would never start.

"Unload, sleep/wait, load" is made concrete rather than literal: the GPU
tool already unloads the model after every clip
(`movie_clip_generation._release_gpu_and_cpu_memory`); the interruptible
sleep between clips IS the "wait for a healthy state" — and it's also
where this loop's own text-planning calls (which don't touch the GPU)
happen, so a text call and a clip call are never in flight at the same
time on this 15GB-RAM machine.
"""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

__all__ = ["run_auto_series"]

_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9 _-]")


def _sanitize_title(raw: str, *, fallback: str) -> str:
    """movie_projects.save() requires titles matching `_NAME_RE` (alnum
    start, then alnum/space/-/_ only, <=81 chars) — an LLM's title can
    easily include punctuation that regex rejects. Strip anything else,
    collapse whitespace, and fall back honestly if nothing usable
    survives, rather than letting save() raise mid-loop."""
    cleaned = _NAME_SAFE_RE.sub("", raw or "").strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)[:80].strip()
    if not cleaned or not cleaned[0].isalnum():
        cleaned = (fallback + " " + cleaned).strip()[:80] if cleaned else fallback
    return cleaned or fallback


async def run_auto_series(
    *,
    data_dir: Path,
    sandbox_dir: Path,
    on_status: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    sleep: Optional[Callable[[float], Awaitable[None]]] = None,
    clock: Optional[Callable[[], float]] = None,
    clip_gap_seconds: float = 20.0,
    poll_seconds: float = 1.0,
    shots_per_episode: int = 3,
    auto_crown_store=None,
    max_iterations: Optional[int] = None,  # test/defensive cap only — never set from the UI
) -> str:
    should_stop = should_stop or (lambda: False)
    sleep = sleep or asyncio.sleep
    clock = clock or time.monotonic

    def _status(msg: str) -> None:
        if on_status is not None:
            try:
                on_status(msg)
            except Exception:  # noqa: BLE001 — a broken UI callback must never break the loop
                pass

    from . import movie_projects, movie_series
    from .auto_crown import get_auto_crown_store
    from .cockpit.movie_generation_actions import run_add_shot, run_advance_episode, run_start_episode
    from .movie_episode_render import EpisodeStore
    from .movie_series_auto import compose_next_beat, compose_series_concept

    store = auto_crown_store or get_auto_crown_store()
    log_dir = Path(sandbox_dir) / "movies"
    ep_store = EpisodeStore(Path(data_dir) / "movie_episodes", Path(sandbox_dir) / "movies")

    def _armed() -> bool:
        session = store.status()
        return session is not None and session.status == "active" and not store.is_expired()

    # Kevin, 2026-07-29: "make sure the bots automatically pause while
    # episodes are being produced... to prevent memory leaks." Paused
    # ONCE for the whole unattended run (not per clip — that would just
    # bounce the Discord gateway connection for hours) and resumed once
    # when the loop exits, however it exits. bot_services calls are sync
    # (real systemctl subprocess calls) — off the event loop via
    # to_thread, same idiom run_advance_episode already uses for its own
    # sync call.
    #
    # ETA (Kevin, same night: "leave an ETA of how long until they
    # should be until they are back online") comes straight from the
    # REAL armed Auto Crown session's own remaining time — a precise,
    # honest number already available, not a guess.
    from . import bot_services
    session_for_eta = store.status()
    eta_minutes = session_for_eta.remaining_minutes() if session_for_eta is not None else None
    bots_were_active, _pause_receipt = await asyncio.to_thread(
        bot_services.pause_for_production, eta_minutes=eta_minutes,
    )

    try:
        iterations = 0
        while True:
            if not _armed():
                _status("Auto Series stopped — no active Auto session")
                return f"stopped — Auto session ended (completed {iterations} clip step(s))"
            if should_stop():
                _status("Auto Series stopped — cancelled")
                return f"stopped — cancelled (completed {iterations} clip step(s))"
            if max_iterations is not None and iterations >= max_iterations:
                return f"stopped — reached max_iterations={max_iterations} (test/defensive cap)"

            focus = movie_projects.get_focus(data_dir)
            project = movie_projects.load_by_slug(focus.slug, data_dir) if focus.slug else None
            opening_beat = None

            if project is None:
                _status("designing a new series…")
                concept = await compose_series_concept(workspace=log_dir)
                genre = concept.genre if concept.genre in dict(movie_projects.MOVIE_GENRES) else "short-film"
                style = concept.style if concept.style in dict(movie_projects.MOVIE_STYLES) else "animated"
                title = _sanitize_title(concept.title, fallback="Auto Series")
                project = movie_projects.MovieProject(
                    title=title, logline=concept.logline[:400], genre=genre, style=style,
                )
                movie_projects.save(project, data_dir)
                movie_projects.set_focus(
                    movie_projects.slugify(title), "Auto Series: new series designed", data_dir,
                )
                opening_beat = concept.opening_beat
                _status(f"designed + focused new series: {title}")

            slug = movie_projects.slugify(project.title)
            episode_focus = movie_series.get_episode_focus(data_dir)
            episode = None
            if episode_focus.episode_id:
                try:
                    episode = ep_store.get(episode_focus.episode_id)
                except Exception:  # noqa: BLE001
                    episode = None

            if episode is None or episode.is_terminal():
                next_episode_number = (episode.episode_number + 1) if episode else 1
                _status(f"writing episode {next_episode_number}'s opening shot…")
                beat = opening_beat or await compose_next_beat(
                    series_title=project.title, prior_beats=[], episode_number=next_episode_number,
                    workspace=log_dir,
                )
                msg = await run_start_episode(slug, beat=beat, data_dir=data_dir, sandbox_dir=sandbox_dir)
                _status(msg)
                episode_focus = movie_series.get_episode_focus(data_dir)
                if not episode_focus.episode_id:
                    _status("Auto Series stopped — could not start an episode")
                    return f"stopped — could not start an episode (completed {iterations} clip step(s))"
                episode = ep_store.get(episode_focus.episode_id)

            current_shot = next((s for s in episode.shots if s.status in ("pending", "in_progress")), None)
            if (current_shot is not None
                    and len(current_shot.clips) >= max(1, current_shot.target_clips) - 1
                    and len(episode.shots) < shots_per_episode):
                # Real gap found + fixed here: without a per-episode shot
                # cap, queuing "one more shot" preemptively every time
                # would repeat forever — an episode would NEVER reach a
                # real terminal state, so a new episode (and thus the
                # rest of the series) would never start. shots_per_episode
                # bounds a single episode to a real, finishable chunk
                # (matches ShotEntry's own docstring: "1-3 minutes of
                # screen time" per shot — a handful of shots is already a
                # real episode's worth).
                has_next_shot = any(s.shot_number > current_shot.shot_number for s in episode.shots)
                if not has_next_shot:
                    _status("writing the next shot…")
                    next_beat = await compose_next_beat(
                        series_title=project.title,
                        prior_beats=[s.beat for s in episode.shots if s.beat],
                        episode_number=episode.episode_number,
                        workspace=log_dir,
                    )
                    add_msg = await run_add_shot(
                        episode.episode_id, next_beat, data_dir=data_dir, sandbox_dir=sandbox_dir,
                    )
                    _status(add_msg)

            _status("advancing one clip…")
            advance_msg = await run_advance_episode(
                episode.episode_id, data_dir=data_dir, sandbox_dir=sandbox_dir,
                on_wait=lambda mb, elapsed: _status(
                    f"please wait — waiting for RAM to clear ({elapsed:.0f}s, {mb}MB available)…"
                ),
                on_step=lambda step, total: _status(f"clip step {step}/{total}…"),
            )
            _status(advance_msg)
            iterations += 1

            # The "graceful sleep schedule": interruptible, checked
            # against both the cancel flag and the Auto session's own
            # expiry so a sleep never outlives its own authorization.
            # Same idiom as self_practice.py's _interruptible_rest,
            # adapted to async.
            start = clock()
            end = start + clip_gap_seconds
            while True:
                now = clock()
                if now >= end or should_stop() or not _armed():
                    break
                await sleep(min(poll_seconds, max(0.0, end - now)))
    finally:
        await asyncio.to_thread(bot_services.resume_after_production, bots_were_active)
