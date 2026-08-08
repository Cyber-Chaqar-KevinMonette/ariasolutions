"""
movie_episode_render_runner — outer driver for an episode render session.
Mirrors dream_runner.advance_dream exactly: ONE call moves the episode
forward by exactly one clip attempt, refusing early on paused/terminal
states, checking caps at the boundary, and persisting after every single
step so a crash never loses more than one in-flight clip.

movie-studio-d Phase 3B (Kevin, 2026-07-28).

One `advance_episode()` call does this:
  1. Load the episode (paused/terminal → refuse, zero writes).
  2. Re-check caps (already-exhausted → mark exhausted, return).
  3. No shots left pending/in_progress → mark completed, return.
  4. Build this shot's prompt from its beat + the series' character bible.
  5. Generate ONE clip: the very first clip of the whole episode uses the
     plain LTX path; every clip after conditions on episode.last_frame_path
     (the continuity cursor, never reset by a retry).
  6. Extract the new clip's last frame, run it through the quality gate.
     PASS -> advance the cursor, mark progress, done. FAIL, under the
     per-clip retry cap -> same slot retried next call, cursor untouched.
     FAIL, retry cap exhausted -> quarantine the bad clip(s), poison the
     shot, auto-pause the whole episode (a human must look at it — never
     silently skip to the next shot on a broken one).
  7. Shot's target_clips reached -> finalize the shot, advance the cursor
     to the next one.

Reserved-not-wired: EpisodeCaps.max_consecutive_shot_failures is meant for
a future multi-shot circuit breaker (many DIFFERENT shots failing in a
row). Not implemented yet — today, ANY single poisoned shot immediately
pauses the episode, which is the conservative default until that breaker
is built.

WorkflowSentinel gets its first real caller anywhere in this repo here —
purely advisory (never gates anything): start/step/stall/error/done/pattern
signals at the obvious lifecycle points, reusing its existing "3 repeats of
the same failure reason -> propose an upgrade" logic unmodified.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .movie_character_bible import build_prompt_for_shot, load_bible
from .movie_clip_generation import generate_clip_async
from .movie_clip_quality_gate import assess_frame
from .movie_episode_render import ClipEntry, EpisodeStore, ShotEntry
from .movie_video_continuity import extract_last_frame
from .workflow_sentinel import WorkflowSentinel

__all__ = ["EpisodeAdvanceResult", "advance_episode", "DEFAULT_NEGATIVE_PROMPT"]

DEFAULT_NEGATIVE_PROMPT = "worst quality, inconsistent motion, blurry, jittery, distorted"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class EpisodeAdvanceResult:
    """Outcome of one advance_episode() call. Mirrors DreamAdvanceResult's
    shape so the CLI can render both consistently."""

    episode_id: str
    episode_status: str
    step_outcome: str   # clip_pass | clip_retry | shot_poisoned_episode_paused
                          # | episode_completed | episode_exhausted
                          # | episode_paused | episode_<terminal>
    shot_number: int = -1
    clip_number: int = -1
    reason: str = ""


def _next_clip_number_and_attempt(shot: ShotEntry) -> tuple[int, int]:
    if not shot.clips:
        return 1, 1
    last = shot.clips[-1]
    if last.quality_status == "pass":
        return last.clip_number + 1, 1
    return last.clip_number, last.attempt + 1


def _quarantine(paths: list[Path], shot_dir: Path) -> None:
    q = shot_dir / "quarantine"
    q.mkdir(parents=True, exist_ok=True)
    for p in paths:
        p = Path(p)
        if p.is_file():
            p.rename(q / p.name)


def advance_episode(
    *,
    episode_id: str,
    store: EpisodeStore,
    data_dir: Path,
    sentinel: WorkflowSentinel | None = None,
) -> EpisodeAdvanceResult:
    episode = store.get(episode_id)
    label = f"movie-render:{episode_id}"

    if episode.status == "paused":
        return EpisodeAdvanceResult(
            episode_id, "paused", "episode_paused",
            reason="episode is paused; resume it first",
        )
    if episode.is_terminal():
        return EpisodeAdvanceResult(
            episode_id, episode.status, f"episode_{episode.status}",
            reason=f"episode is {episode.status}",
        )

    exhausted, reason = episode.caps_check()
    if exhausted:
        episode.status = "exhausted"
        episode.notes = (episode.notes + "\n" if episode.notes else "") + f"EXHAUSTED: {reason}"
        store.save(episode)
        if sentinel:
            sentinel.observe_event("error", label, reason)
        return EpisodeAdvanceResult(episode_id, "exhausted", "episode_exhausted", reason=reason)

    shot = next((s for s in episode.shots if s.status in ("pending", "in_progress")), None)
    if shot is None:
        episode.status = "completed"
        store.save(episode)
        if sentinel:
            sentinel.observe_event("done", label)
        return EpisodeAdvanceResult(episode_id, "completed", "episode_completed",
                                     reason="no shots left to render")

    if shot.status == "pending":
        shot.status = "in_progress"
        shot.started_at = _utc_now()
        if sentinel:
            sentinel.observe_event("start", label, f"shot {shot.shot_number}")

    bible = load_bible(episode.series_slug, data_dir)
    prompt, negative_prompt = build_prompt_for_shot(
        shot.beat, shot.characters_present, bible, DEFAULT_NEGATIVE_PROMPT
    )

    clip_number, attempt = _next_clip_number_and_attempt(shot)
    work_dir = Path(episode.work_dir)
    shot_dir = work_dir / f"shot-{shot.shot_number:03d}"
    shot_dir.mkdir(parents=True, exist_ok=True)
    out_path = shot_dir / f"clip-{clip_number:03d}-attempt-{attempt:02d}.mp4"

    condition_image_path = Path(episode.last_frame_path) if episode.last_frame_path else None

    started = time.monotonic()
    try:
        asyncio.run(generate_clip_async(
            prompt=prompt, negative_prompt=negative_prompt, out_path=out_path,
            condition_image_path=condition_image_path,
        ))
    except Exception as exc:  # noqa: BLE001
        episode.elapsed_seconds += time.monotonic() - started
        return _record_failure(
            episode, shot, clip_number, attempt, out_path, None,
            f"generation_error: {type(exc).__name__}: {str(exc)[:200]}",
            store, sentinel, label,
        )
    episode.elapsed_seconds += time.monotonic() - started

    frame_result = extract_last_frame(out_path)
    if not frame_result.ok:
        return _record_failure(
            episode, shot, clip_number, attempt, out_path, None,
            f"frame_extraction_failed: {frame_result.detail}", store, sentinel, label,
        )

    verdict = assess_frame(Path(frame_result.path))
    if not verdict.passed:
        return _record_failure(
            episode, shot, clip_number, attempt, out_path, frame_result.path,
            f"quality_gate_failed: {verdict.reason}", store, sentinel, label,
        )

    # ── PASS ──────────────────────────────────────────────────────────
    shot.clips.append(ClipEntry(
        clip_number=clip_number, path=str(out_path), attempt=attempt,
        quality_status="pass", quality_reason=verdict.reason,
        started_at=_utc_now(), ended_at=_utc_now(),
    ))
    shot.last_frame_path = frame_result.path
    shot.consecutive_failures = 0
    episode.last_frame_path = frame_result.path
    episode.clips_completed += 1
    if sentinel:
        sentinel.observe_event("step", label, f"shot {shot.shot_number} clip {clip_number}")

    step_outcome = "clip_pass"
    if len(shot.clips) >= shot.target_clips:
        shot.status = "done"
        shot.ended_at = _utc_now()
        episode.shots_completed += 1
        episode.current_shot_index += 1
        step_outcome = "shot_done"

    # Post-clip cap re-check (a clip might have just pushed elapsed_seconds
    # or clips_completed past a cap — refused at the NEXT boundary, same
    # semantics as dream.py).
    exhausted, reason = episode.caps_check()
    if exhausted:
        episode.status = "exhausted"
        episode.notes = (episode.notes + "\n" if episode.notes else "") + f"EXHAUSTED: {reason}"
        store.save(episode)
        if sentinel:
            sentinel.observe_event("done", label)
        return EpisodeAdvanceResult(episode_id, "exhausted", "episode_exhausted",
                                     shot.shot_number, clip_number, reason=reason)

    store.save(episode)
    return EpisodeAdvanceResult(episode_id, episode.status, step_outcome,
                                 shot.shot_number, clip_number, reason=verdict.reason)


def _record_failure(
    episode, shot: ShotEntry, clip_number: int, attempt: int,
    clip_path: Path, frame_path: str | None, reason: str,
    store: EpisodeStore, sentinel: WorkflowSentinel | None, label: str,
) -> EpisodeAdvanceResult:
    shot.clips.append(ClipEntry(
        clip_number=clip_number, path=str(clip_path), attempt=attempt,
        quality_status="failed_retry", quality_reason=reason,
        started_at=_utc_now(), ended_at=_utc_now(),
    ))
    shot.consecutive_failures += 1
    if sentinel:
        sentinel.observe_event("stall", label, reason)
        sentinel.observe_event("pattern", label, reason)

    if shot.consecutive_failures > episode.caps.max_retries_per_clip:
        shot.clips[-1].quality_status = "quarantined"
        shot_dir = Path(episode.work_dir) / f"shot-{shot.shot_number:03d}"
        to_quarantine = [clip_path]
        if frame_path:
            to_quarantine.append(Path(frame_path))
        _quarantine(to_quarantine, shot_dir)

        shot.status = "poisoned"
        episode.status = "paused"
        episode.notes = (
            (episode.notes + "\n" if episode.notes else "")
            + f"AUTO-PAUSED: shot {shot.shot_number} exceeded "
              f"max_retries_per_clip ({episode.caps.max_retries_per_clip}): {reason}"
        )
        store.save(episode)
        if sentinel:
            sentinel.observe_event("error", label, "shot poisoned; episode auto-paused")
        return EpisodeAdvanceResult(
            episode.episode_id, "paused", "shot_poisoned_episode_paused",
            shot.shot_number, clip_number, reason=reason,
        )

    store.save(episode)
    return EpisodeAdvanceResult(
        episode.episode_id, episode.status, "clip_retry",
        shot.shot_number, clip_number, reason=reason,
    )
