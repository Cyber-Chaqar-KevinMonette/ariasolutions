"""movie_episode_health — real, file-level verification that an episode's
bookkeeping matches reality, never trusted blindly.

Kevin, 2026-07-29: "Let's add a episode verify health and success auto
checking feature after every episode to verify it's an healthy episode."
Directly motivated by a real incident the same night: an episode whose
only shot failed every generation attempt (a real `ModuleNotFoundError:
No module named 'torch'`) still got marked `completed` — the shot-picker
in `movie_episode_render_runner.advance_episode` only recognizes
`("pending", "in_progress")` shots, so a `poisoned` shot was invisible to
it, and "no shots left to look at" was silently read as "everything
succeeded." That specific hole is fixed at the source now, but this
module is the general defense-in-depth version of the same lesson: an
episode's in-memory status is a claim, not a fact — before anything is
allowed to call an episode genuinely done, every "done" shot's "passing"
clips get checked for real, on disk, via ffprobe (same house style as
`movie_video_continuity.extract_last_frame`: shutil.which discovery,
subprocess.run(capture_output=True, timeout=...), never raises).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

__all__ = ["ClipHealthIssue", "EpisodeHealthReport", "probe_clip", "verify_episode_health"]

ProbeFn = Callable[[Path], "tuple[bool, str]"]


@dataclass
class ClipHealthIssue:
    shot_number: int
    clip_number: Optional[int]
    path: Optional[str]
    problem: str

    def __str__(self) -> str:
        where = f"shot {self.shot_number}"
        if self.clip_number is not None:
            where += f" clip {self.clip_number}"
        return f"{where}: {self.problem}"


@dataclass
class EpisodeHealthReport:
    episode_id: str
    healthy: bool
    shots_checked: int
    clips_verified: int
    issues: list[ClipHealthIssue] = field(default_factory=list)

    def summary(self) -> str:
        if self.healthy:
            return (f"health check passed — {self.shots_checked} shot(s), "
                    f"{self.clips_verified} clip(s) verified real on disk")
        lines = [f"health check FAILED — {len(self.issues)} issue(s):"]
        lines.extend(f"  {issue}" for issue in self.issues)
        return "\n".join(lines)


def probe_clip(path: Path, *, timeout: int = 15) -> tuple[bool, str]:
    """Real ffprobe check: the file must exist, be non-empty, and be a
    playable video with at least one real frame and non-zero duration.
    Never raises — a missing binary, a corrupt file, or a timeout all
    degrade to (False, reason) so a caller's loop never needs its own
    try/except."""
    path = Path(path)
    if not path.is_file():
        return False, f"file not found: {path}"
    if path.stat().st_size == 0:
        return False, f"file is empty (0 bytes): {path}"

    backend = shutil.which("ffprobe")
    if backend is None:
        return False, "ffprobe not installed — cannot verify this clip"

    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=nb_read_frames,duration", "-of", "csv=p=0", str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[:200]
            return False, f"ffprobe failed: {stderr}"
        out = result.stdout.decode("utf-8", errors="replace").strip()
        parts = out.split(",")
        if len(parts) < 2:
            return False, f"ffprobe returned unexpected output: {out!r}"
        # ffprobe's csv=p=0 output orders fields as "duration,nb_read_frames"
        # (confirmed empirically — NOT the order given to -show_entries).
        try:
            duration = float(parts[0])
        except ValueError:
            duration = 0.0
        frames = int(parts[1]) if parts[1].strip().isdigit() else 0
        if frames <= 0:
            return False, f"clip has zero real frames (ffprobe reported {frames!r})"
        if duration <= 0:
            return False, f"clip has zero duration (ffprobe reported {duration!r})"
        return True, f"{frames} frame(s), {duration:.3f}s"
    except subprocess.TimeoutExpired:
        return False, f"ffprobe timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"probe error: {type(exc).__name__}: {exc}"


def verify_episode_health(episode, *, probe: Optional[ProbeFn] = None) -> EpisodeHealthReport:
    """Never trusts `shot.status`/`clip.quality_status` alone. A shot
    marked "poisoned" makes the episode unhealthy regardless of anything
    else (it never produced a passing clip, by definition). A shot marked
    "done" must actually have >= target_clips clips with quality_status
    == "pass" — and every one of those clips gets probed for real on
    disk. An episode with zero shots at all is also flagged (nothing was
    ever queued, so "nothing left to render" can't mean "succeeded")."""
    probe = probe or probe_clip
    issues: list[ClipHealthIssue] = []
    clips_verified = 0

    if not episode.shots:
        issues.append(ClipHealthIssue(
            shot_number=0, clip_number=None, path=None,
            problem="episode has zero shots — nothing was ever queued to render",
        ))

    for shot in episode.shots:
        if shot.status == "poisoned":
            issues.append(ClipHealthIssue(
                shot.shot_number, None, None,
                "shot is poisoned — it never produced a passing clip",
            ))
            continue
        if shot.status != "done":
            continue  # still pending/in_progress — not this check's business yet
        passing = [c for c in shot.clips if c.quality_status == "pass"]
        if len(passing) < shot.target_clips:
            issues.append(ClipHealthIssue(
                shot.shot_number, None, None,
                f"marked done but only {len(passing)}/{shot.target_clips} clips actually passed",
            ))
            continue
        for clip in passing:
            ok, detail = probe(Path(clip.path))
            if not ok:
                issues.append(ClipHealthIssue(shot.shot_number, clip.clip_number, clip.path, detail))
            else:
                clips_verified += 1

    return EpisodeHealthReport(
        episode_id=episode.episode_id, healthy=not issues,
        shots_checked=len(episode.shots), clips_verified=clips_verified, issues=issues,
    )
