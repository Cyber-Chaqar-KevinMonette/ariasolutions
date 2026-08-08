"""
movie_episode_render — a long-lived, pauseable, resumable, cap-bounded
episode render session. Structurally a direct mirror of dream.py's
DreamSession/DreamCaps/CycleEntry/DreamStore (same fcntl-lock discipline,
same atomic-YAML-write discipline, same "caps checked at boundaries, not
mid-unit" semantics) — see dream.py for the fuller rationale essay this
borrows from.

movie-studio-d Phase 3 (Kevin, 2026-07-28): "Devise a system where 1-3
minute[shots] can chain turns to make full production [episodes]... by
taking the last frame of the last [clip] and an intelligent helper system
to carry the last frame and the story forward with surgical and precision
accuracy... Fill in any gaps I could be missing to make this scale."

Why a shot/clip cursor instead of forcing this into dream.py's own cycle
shape: a dream cycle is an LLM-authored software-build step; an episode's
unit of work is a GPU video-generation call with its own failure mode
(a blank/washed-out frame) that dream cycles don't have — quality_status
per clip and a bounded per-clip retry/quarantine path are genuinely new
concepts, not a relabeling of CycleEntry.

Honest scale note (see the Movie Studio Phase 3 plan's full scale math):
the only proven clip size as of this build is ~9 frames (~1.1s). Reaching
a genuine "1-3 minute shot" or "20-60 minute episode" means chaining MANY
clips — this module provides the chaining/pause/resume/quality-gate
mechanism; how long a shot or episode actually gets to be is a caps/beat-
sheet decision made by the caller, never a promise baked in here.

Storage layout:
  <data_dir>/movie_episodes/<episode_id>.yaml       — the session record
  <data_dir>/movie_episodes/<episode_id>.yaml.lock  — fcntl lock file
  <sandbox_dir>/movies/<series>/<season>/<episode_id>/  — clip files
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from ulid import ULID

__all__ = [
    "ClipEntry",
    "EpisodeCaps",
    "EpisodeCorrupt",
    "EpisodeError",
    "EpisodeExhausted",
    "EpisodeLocked",
    "EpisodeNotFound",
    "EpisodeRenderSession",
    "EpisodeStore",
    "HARD_CAP_SHOTS",
    "ShotEntry",
    "count_clip_files_under",
    "new_episode_id",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


EpisodeStatus = Literal["active", "paused", "completed", "exhausted", "halted"]

_VALID_EPISODE_STATUSES: frozenset[str] = frozenset(
    {"active", "paused", "completed", "exhausted", "halted"}
)
_VALID_SHOT_STATUSES: frozenset[str] = frozenset({"pending", "in_progress", "done", "poisoned"})
_VALID_QUALITY_STATUSES: frozenset[str] = frozenset(
    {"pending", "pass", "failed_retry", "quarantined"}
)

# Backstop only, same role as dream.py's HARD_CAP_CYCLES — operators hit
# their own EpisodeCaps.max_shots long before this.
HARD_CAP_SHOTS = 100_000


# ─── Errors ─────────────────────────────────────────────────────────────────


class EpisodeError(Exception):
    """Base for episode-render-session errors."""


class EpisodeNotFound(EpisodeError):
    pass


class EpisodeCorrupt(EpisodeError):
    """Malformed episode-session YAML."""


class EpisodeExhausted(EpisodeError):
    """A cap has been reached. Caller should stop."""


class EpisodeLocked(EpisodeError):
    """Episode YAML is locked by another runner."""


# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass
class EpisodeCaps:
    """Soft caps bounding one episode's lifetime. All fields nullable
    (except the retry/failure counters); None or 0 == unbounded. Checked
    at shot boundaries, not mid-shot — a shot in flight is allowed to
    finish its current clip attempt."""

    max_shots: int | None = None
    max_clips_total: int | None = None
    max_seconds: float | None = None
    max_retries_per_clip: int = 3
    max_consecutive_shot_failures: int = 2

    def is_exceeded(
        self, *, shots_completed: int, clips_completed: int, elapsed_seconds: float
    ) -> tuple[bool, str]:
        if self.max_shots is not None and self.max_shots > 0 and shots_completed >= self.max_shots:
            return True, f"max_shots reached ({shots_completed}/{self.max_shots})"
        if (
            self.max_clips_total is not None
            and self.max_clips_total > 0
            and clips_completed >= self.max_clips_total
        ):
            return True, f"max_clips_total reached ({clips_completed}/{self.max_clips_total})"
        if (
            self.max_seconds is not None
            and self.max_seconds > 0
            and elapsed_seconds >= self.max_seconds
        ):
            return True, f"max_seconds reached ({elapsed_seconds:.0f}/{self.max_seconds:.0f}s)"
        return False, ""


@dataclass
class ClipEntry:
    """One generated clip — the atomic unit inside a shot."""

    clip_number: int
    path: str = ""
    attempt: int = 1
    seed: int | None = None
    quality_status: str = "pending"   # pending | pass | failed_retry | quarantined
    quality_reason: str = ""
    started_at: str = ""
    ended_at: str | None = None


@dataclass
class ShotEntry:
    """One shot (1-3 minutes of screen time, built from chained clips).

    target_clips is the caller's own beat-sheet decision (how many chained
    clips this shot needs at whatever clip size was configured) — never a
    value this module invents. A shot is "done" once len(clips-that-passed)
    reaches target_clips.
    """

    shot_number: int
    beat: str = ""
    characters_present: list[str] = field(default_factory=list)
    target_clips: int = 1
    status: str = "pending"   # pending | in_progress | done | poisoned
    clips: list[ClipEntry] = field(default_factory=list)
    last_frame_path: str | None = None
    consecutive_failures: int = 0
    started_at: str = ""
    ended_at: str | None = None


@dataclass
class EpisodeRenderSession:
    """A long-running chained-clip render with caps + a continuity cursor.

    Read freely. Mutations should go through EpisodeStore.save() or the
    EpisodeStore.lock() contextmanager so they persist atomically.
    """

    episode_id: str
    series_slug: str
    season_id: str
    episode_number: int
    title: str
    caps: EpisodeCaps = field(default_factory=EpisodeCaps)
    status: EpisodeStatus = "active"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    # Cursor state — grows monotonically across shots
    shots_completed: int = 0
    clips_completed: int = 0
    elapsed_seconds: float = 0.0
    current_shot_index: int = 0

    # THE continuity cursor — None only before the very first clip exists.
    last_frame_path: str | None = None

    shots: list[ShotEntry] = field(default_factory=list)

    # Working dir under <sandbox_dir>/movies/<series>/<season>/<episode_id>/
    work_dir: str = ""

    notes: str = ""

    def is_terminal(self) -> bool:
        return self.status in ("completed", "exhausted", "halted")

    def caps_check(self) -> tuple[bool, str]:
        return self.caps.is_exceeded(
            shots_completed=self.shots_completed,
            clips_completed=self.clips_completed,
            elapsed_seconds=self.elapsed_seconds,
        )

    def progress_summary(self) -> str:
        parts = [f"{self.shots_completed} shots", f"{self.clips_completed} clips"]
        if self.caps.max_shots:
            parts.append(f"(of {self.caps.max_shots} max shots)")
        return " · ".join(parts)


# ─── Episode IDs ────────────────────────────────────────────────────────────


def new_episode_id(season_id: str, episode_number: int) -> str:
    """'ep-<season_id>-e<NN>-<ulid7>'. season_id already carries the series
    slug + season number, so this isn't duplicated here."""
    short = str(ULID()).lower()[-7:]
    return f"ep-{season_id}-e{episode_number:02d}-{short}"


# ─── Store ──────────────────────────────────────────────────────────────────


class EpisodeStore:
    """Filesystem-backed episode-render-session registry. Mirrors
    dream.DreamStore's fcntl-lock discipline exactly — see dream.py's
    DreamStore docstring for the full rationale."""

    def __init__(self, root: Path, work_root: Path):
        self.root = Path(root)
        self.work_root = Path(work_root)

    def _path(self, episode_id: str) -> Path:
        if not _is_safe_id(episode_id):
            raise EpisodeError(f"invalid episode_id: {episode_id!r}")
        return self.root / f"{episode_id}.yaml"

    def _lock_path(self, episode_id: str) -> Path:
        return self._path(episode_id).with_suffix(".yaml.lock")

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)

    def work_dir_for(self, episode_id: str) -> Path:
        return self.work_root / episode_id

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("ep-*.yaml") if p.is_file())

    def list_all(self, *, status: str | None = None) -> list[EpisodeRenderSession]:
        out: list[EpisodeRenderSession] = []
        for eid in self.list_ids():
            try:
                e = self.get(eid)
            except EpisodeError:
                continue
            if status is None or e.status == status:
                out.append(e)
        return out

    def exists(self, episode_id: str) -> bool:
        return self._path(episode_id).exists()

    def get(self, episode_id: str) -> EpisodeRenderSession:
        path = self._path(episode_id)
        if not path.exists():
            raise EpisodeNotFound(episode_id)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise EpisodeCorrupt(f"YAML parse error in {path}: {e}") from e
        if not isinstance(data, dict):
            raise EpisodeCorrupt(f"episode {episode_id}: root must be a mapping")
        return _from_yaml(data)

    def save(self, episode: EpisodeRenderSession) -> None:
        self.ensure_root()
        path = self._path(episode.episode_id)
        episode.updated_at = _utc_now()
        _atomic_write_text(path, yaml.safe_dump(_to_yaml(episode), sort_keys=False))

    @contextlib.contextmanager
    def lock(self, episode_id: str, *, blocking: bool = True, timeout_seconds: float = 30.0):
        """fcntl-backed exclusive lock. Yields the loaded session; mutations
        persist on clean exit only (exceptions propagate without saving)."""
        import fcntl
        import time
        if not self.exists(episode_id):
            raise EpisodeNotFound(episode_id)
        self.ensure_root()
        lock_path = self._lock_path(episode_id)
        lock_path.touch(exist_ok=True)
        f = lock_path.open("r+")
        try:
            if blocking and timeout_seconds:
                deadline = time.monotonic() + timeout_seconds
                acquired = False
                while time.monotonic() < deadline:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                        break
                    except BlockingIOError:
                        time.sleep(0.1)
                if not acquired:
                    raise EpisodeLocked(
                        f"could not acquire lock on episode {episode_id} within {timeout_seconds}s"
                    )
            else:
                mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                try:
                    fcntl.flock(f.fileno(), mode)
                except BlockingIOError as e:
                    raise EpisodeLocked(f"episode {episode_id} is locked") from e

            episode = self.get(episode_id)
            yield episode
            self.save(episode)
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            f.close()

    def create(
        self,
        *,
        series_slug: str,
        season_id: str,
        episode_number: int,
        title: str,
        caps: EpisodeCaps | None = None,
        notes: str = "",
        episode_id: str | None = None,
    ) -> EpisodeRenderSession:
        """Create a new episode render session. episode_id=None mints a
        fresh ULID-suffixed id; pre-supplying one is a test hook (raises
        FileExistsError on collision)."""
        self.ensure_root()
        eid = episode_id or new_episode_id(season_id, episode_number)
        path = self._path(eid)
        if path.exists():
            raise FileExistsError(f"episode {eid} already exists at {path}")

        work = self.work_dir_for(eid)
        work.mkdir(parents=True, exist_ok=True)

        episode = EpisodeRenderSession(
            episode_id=eid,
            series_slug=series_slug,
            season_id=season_id,
            episode_number=episode_number,
            title=title,
            caps=caps or EpisodeCaps(),
            work_dir=str(work),
            notes=notes,
        )
        self.save(episode)
        return episode

    def delete(self, episode_id: str, *, delete_work_dir: bool = False) -> bool:
        path = self._path(episode_id)
        existed = path.exists()
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        if delete_work_dir:
            work = self.work_dir_for(episode_id)
            if work.exists():
                import shutil
                shutil.rmtree(work, ignore_errors=True)
        return existed


def _is_safe_id(episode_id: str) -> bool:
    if not episode_id:
        return False
    return all(c.isalnum() or c in "-_." for c in episode_id)


# ─── Serialization ──────────────────────────────────────────────────────────


def _to_yaml(e: EpisodeRenderSession) -> dict:
    return {
        "episode_id": e.episode_id,
        "series_slug": e.series_slug,
        "season_id": e.season_id,
        "episode_number": e.episode_number,
        "title": e.title,
        "status": e.status,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
        "caps": {
            "max_shots": e.caps.max_shots,
            "max_clips_total": e.caps.max_clips_total,
            "max_seconds": e.caps.max_seconds,
            "max_retries_per_clip": e.caps.max_retries_per_clip,
            "max_consecutive_shot_failures": e.caps.max_consecutive_shot_failures,
        },
        "shots_completed": e.shots_completed,
        "clips_completed": e.clips_completed,
        "elapsed_seconds": e.elapsed_seconds,
        "current_shot_index": e.current_shot_index,
        "last_frame_path": e.last_frame_path,
        "work_dir": e.work_dir,
        "notes": e.notes,
        "shots": [_shot_to_yaml(s) for s in e.shots],
    }


def _shot_to_yaml(s: ShotEntry) -> dict:
    d = asdict(s)
    return d


def _from_yaml(data: dict) -> EpisodeRenderSession:
    try:
        episode_id = str(data["episode_id"])
        series_slug = str(data["series_slug"])
        season_id = str(data["season_id"])
        episode_number = int(data["episode_number"])
        title = str(data["title"])
    except KeyError as e:
        raise EpisodeCorrupt(f"missing required field: {e.args[0]}") from None

    status = str(data.get("status", "active"))
    if status not in _VALID_EPISODE_STATUSES:
        raise EpisodeCorrupt(f"invalid status: {status!r}")

    raw_caps = data.get("caps") or {}
    caps = EpisodeCaps(
        max_shots=_int_or_none(raw_caps.get("max_shots")),
        max_clips_total=_int_or_none(raw_caps.get("max_clips_total")),
        max_seconds=_float_or_none(raw_caps.get("max_seconds")),
        max_retries_per_clip=int(raw_caps.get("max_retries_per_clip", 3)),
        max_consecutive_shot_failures=int(raw_caps.get("max_consecutive_shot_failures", 2)),
    )

    raw_shots = data.get("shots") or []
    if not isinstance(raw_shots, list):
        raise EpisodeCorrupt("'shots' must be a list")
    shots: list[ShotEntry] = []
    for rs in raw_shots:
        if not isinstance(rs, dict):
            continue
        shots.append(_shot_from_dict(rs))

    return EpisodeRenderSession(
        episode_id=episode_id,
        series_slug=series_slug,
        season_id=season_id,
        episode_number=episode_number,
        title=title,
        caps=caps,
        status=status,  # type: ignore[arg-type]
        created_at=str(data.get("created_at") or _utc_now()),
        updated_at=str(data.get("updated_at") or _utc_now()),
        shots_completed=int(data.get("shots_completed", 0)),
        clips_completed=int(data.get("clips_completed", 0)),
        elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
        current_shot_index=int(data.get("current_shot_index", 0)),
        last_frame_path=data.get("last_frame_path"),
        shots=shots,
        work_dir=str(data.get("work_dir") or ""),
        notes=str(data.get("notes") or ""),
    )


def _shot_from_dict(rs: dict) -> ShotEntry:
    status = str(rs.get("status", "pending"))
    if status not in _VALID_SHOT_STATUSES:
        status = "pending"
    raw_clips = rs.get("clips") or []
    clips: list[ClipEntry] = []
    for rc in raw_clips:
        if not isinstance(rc, dict):
            continue
        qs = str(rc.get("quality_status", "pending"))
        if qs not in _VALID_QUALITY_STATUSES:
            qs = "pending"
        clips.append(ClipEntry(
            clip_number=int(rc.get("clip_number", 0)),
            path=str(rc.get("path", "")),
            attempt=int(rc.get("attempt", 1)),
            seed=_int_or_none(rc.get("seed")),
            quality_status=qs,
            quality_reason=str(rc.get("quality_reason", "")),
            started_at=str(rc.get("started_at", "")),
            ended_at=rc.get("ended_at"),
        ))
    return ShotEntry(
        shot_number=int(rs.get("shot_number", 0)),
        beat=str(rs.get("beat", "")),
        characters_present=list(rs.get("characters_present") or []),
        target_clips=int(rs.get("target_clips", 1)),
        status=status,
        clips=clips,
        last_frame_path=rs.get("last_frame_path"),
        consecutive_failures=int(rs.get("consecutive_failures", 0)),
        started_at=str(rs.get("started_at", "")),
        ended_at=rs.get("ended_at"),
    )


def _int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    """Same shape as dream._atomic_write_text / continuation._atomic_write_text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


# ─── File counting ──────────────────────────────────────────────────────────


def count_clip_files_under(root: Path) -> int:
    """Count clip files under root, recursive, skipping quarantine/.git —
    same semantics as dream.count_files_under."""
    if not root.exists():
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        parts = dirpath.split(os.sep)
        if ".git" in parts or "quarantine" in parts:
            continue
        dirnames[:] = [d for d in dirnames if d not in (".git", "quarantine")]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if full.is_symlink():
                    continue
                if full.is_file():
                    total += 1
            except OSError:
                continue
    return total
