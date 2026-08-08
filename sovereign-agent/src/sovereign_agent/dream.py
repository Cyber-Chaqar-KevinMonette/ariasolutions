"""
╔══════════════════════════════════════════════════════════════════════════╗
║  dream.py — Infinite trillion-dollar software builder sessions            ║
║  v0.2.12                                                                  ║
║                                                                           ║
║  A dream-session is a long-lived, pauseable, resumable, file-cap-bounded  ║
║  iterator over "ideate-architect-build-document-atomize" cycles. Each     ║
║  cycle is itself a continuation in continuations/ — so the existing       ║
║  re-trigger architecture, lock discipline, and step-level safety story    ║
║  apply unchanged. The dream-session is just the outer cursor.             ║
║                                                                           ║
║  Why a separate file instead of an extra continuation field?              ║
║                                                                           ║
║    • A continuation has a fixed, deterministic step list. A dream-session ║
║      generates new cycles indefinitely, so its step count isn't known     ║
║      at plan time. Forcing it into the continuation contract would break  ║
║      the "deterministic plan from inputs" property that makes the         ║
║      re-trigger architecture auditable.                                   ║
║                                                                           ║
║    • Caps live on the dream, not the cycles. If the operator says "stop  ║
║      at 2000 files" they're capping the *aggregate*, not any one          ║
║      cycle. A separate type cleanly carries that cursor.                  ║
║                                                                           ║
║    • Pause/resume is a dream-level concern. The cycles inherit it via     ║
║      the runner refusing to advance when ``dream.status == 'paused'``.    ║
║                                                                           ║
║  Storage layout:                                                          ║
║    <data_dir>/dream-sessions/<dream_id>.yaml      — the session record    ║
║    <data_dir>/dreams/<dream_id>/                  — the per-dream working ║
║                                  cycle-001/                                ║
║                                    idea.md                                ║
║                                    architecture.md                        ║
║                                    src/...                                ║
║                                    README.md                              ║
║                                  cycle-002/                               ║
║                                    ...                                    ║
║                                                                           ║
║  Continuation IDs: each cycle gets its own task_id like                   ║
║    cycle-<dream_id_short>-001                                             ║
║  so an operator can use the existing ``sov continuations show`` tooling   ║
║  on any cycle directly.                                                   ║
║                                                                           ║
║  Caps semantics:                                                          ║
║    max_files:    aggregate file count under <dreams>/<dream_id>/.         ║
║                  Refused at *next-cycle-start*, not mid-cycle. The cycle  ║
║                  in flight is allowed to finish.                          ║
║    max_cycles:   stop after this many cycles complete.                    ║
║    max_seconds:  total wall time (sum of cycle elapsed). Same             ║
║                  refused-at-cycle-boundary semantics.                     ║
║                                                                           ║
║  Honest limits / what this is NOT:                                        ║
║    • A safeguard against runaway model token cost — that's the per-step   ║
║      budget's job. The dream-runner inherits whatever budgets the         ║
║      operator passes through. No "spent $X" enforcement.                  ║
║    • A guarantee of trillion-dollar quality — the model writes whatever   ║
║      it writes. The infrastructure just doesn't get in its way.           ║
║    • A replacement for the operator's judgment — a paused dream is more   ║
║      useful than a runaway one. Pausing is a feature, not a fallback.    ║
╚══════════════════════════════════════════════════════════════════════════╝
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


DreamStatus = Literal["active", "paused", "completed", "exhausted", "halted"]

_VALID_DREAM_STATUSES: frozenset[str] = frozenset(
    {"active", "paused", "completed", "exhausted", "halted"}
)


# Hard-cap on cycle count regardless of operator settings — prevents runaway
# YAML growth. 100,000 cycles at the typical ~5 files/cycle == 500,000 files
# which is far past any reasonable max_files cap. Operators will hit
# max_files long before this. Exists as a backstop, not a usable knob.
HARD_CAP_CYCLES = 100_000


# ─── Errors ─────────────────────────────────────────────────────────────────


class DreamError(Exception):
    """Base for dream-session errors."""


class DreamNotFound(DreamError):
    pass


class DreamCorrupt(DreamError):
    """Malformed dream-session YAML."""


class DreamExhausted(DreamError):
    """A cap has been reached. Caller should stop."""


class DreamLocked(DreamError):
    """Dream YAML is locked by another runner. v0.2.13."""


# ─── Data shapes ────────────────────────────────────────────────────────────


@dataclass
class DreamCaps:
    """Soft caps that bound a dream's lifetime.

    All fields nullable. None == unbounded. Caps are checked at cycle
    boundaries, NOT mid-cycle, so a single cycle can briefly exceed
    a cap (typically by a handful of files) before the next cycle is
    refused. This keeps cycles atomic.

    Defaults: max_files=2000 (matches the operator's "stop at 2000" ask).
    Operators can pass max_files=0 explicitly to mean unbounded.
    """

    max_files: int | None = 2000
    max_cycles: int | None = None
    max_seconds: float | None = None

    def is_exceeded(
        self,
        *,
        files_written: int,
        cycles_completed: int,
        elapsed_seconds: float,
    ) -> tuple[bool, str]:
        """Check every cap; return (True, reason) on first hit, else (False, '').

        Reason strings are short, human-friendly, used directly in CLI
        messages and event payloads. Edit them in one place — here.
        """
        if self.max_files is not None and self.max_files > 0 and files_written >= self.max_files:
            return True, f"max_files reached ({files_written}/{self.max_files})"
        if self.max_cycles is not None and self.max_cycles > 0 and cycles_completed >= self.max_cycles:
            return True, f"max_cycles reached ({cycles_completed}/{self.max_cycles})"
        if (
            self.max_seconds is not None
            and self.max_seconds > 0
            and elapsed_seconds >= self.max_seconds
        ):
            return True, f"max_seconds reached ({elapsed_seconds:.0f}/{self.max_seconds:.0f}s)"
        return False, ""


@dataclass
class CycleEntry:
    """One completed (or attempted) cycle in a dream's history.

    Stores enough to drive the resume case without re-reading every cycle's
    continuation YAML. ``task_id`` points at the underlying continuation;
    ``files_written`` is the count produced by THIS cycle (delta), not a
    running total — the running total lives on the dream itself.
    """

    cycle_number: int
    task_id: str                  # the continuation that ran this cycle
    started_at: str
    ended_at: str | None = None
    status: str = "in_progress"   # in_progress | done | poisoned | paused
    cycle_dir: str = ""           # absolute path under <data>/dreams/<dream>/cycle-N/
    title: str = ""               # the trillion-dollar idea, one line
    files_written: int = 0
    elapsed_seconds: float = 0.0
    notes: str = ""
    # v0.2.13 — novelty tracking for idle-cycle detection. The atomize
    # step records how many NEW atoms it actually wrote (vs how many were
    # already in atoms.db). Cycles with low novelty count are flagged.
    atoms_written: int = 0
    # v0.2.13 — validator/quarantine accounting. files_written is the
    # GOOD count (passed validation). quarantined_count is files we
    # moved aside as broken syntax/parse failures.
    quarantined_count: int = 0


@dataclass
class ProjectRef:
    """A project the dream is aware of.

    The dream-runner reads these on each cycle's ideate step so the model
    knows what the operator's existing world looks like. When the operator
    runs ``sov projects update <name>``, atomize_diff writes atoms; the
    ideate step retrieves them via memory_search. So this is more of a
    registration list than a knowledge channel — the *atoms* are the
    channel.
    """

    name: str
    root: str
    last_seen_snapshot_at: str = ""


@dataclass
class DreamSession:
    """A long-running ideate→build session with caps + cursor.

    Read freely. Mutations should be wrapped in ``DreamStore.save()`` or
    the convenience ``DreamStore.update(...)`` context manager so they
    are persisted atomically.
    """

    dream_id: str
    goal: str
    caps: DreamCaps = field(default_factory=DreamCaps)
    status: DreamStatus = "active"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    # Cursor state — these grow monotonically across cycles
    cycles_completed: int = 0
    files_written: int = 0
    elapsed_seconds: float = 0.0

    # The currently-running cycle, or None between cycles. The dream-runner
    # sets this when it spawns a cycle and clears it when the cycle drains.
    current_cycle_task_id: str | None = None

    cycles: list[CycleEntry] = field(default_factory=list)
    projects: list[ProjectRef] = field(default_factory=list)

    # Working dir under <data_dir>/dreams/<dream_id>/. Stored explicitly so
    # the dream record is self-describing and we don't have to recompute
    # paths from XDG every read.
    work_dir: str = ""

    notes: str = ""

    def is_terminal(self) -> bool:
        return self.status in ("completed", "exhausted", "halted")

    def caps_check(self) -> tuple[bool, str]:
        """Are we already past a cap? Used at the top of each cycle plan."""
        return self.caps.is_exceeded(
            files_written=self.files_written,
            cycles_completed=self.cycles_completed,
            elapsed_seconds=self.elapsed_seconds,
        )

    def progress_summary(self) -> str:
        """One-line, human-friendly progress for the CLI."""
        parts = [
            f"{self.cycles_completed} cycles",
            f"{self.files_written} files",
        ]
        if self.caps.max_files:
            parts.append(f"(of {self.caps.max_files} max)")
        return " · ".join(parts)


# ─── Dream IDs ──────────────────────────────────────────────────────────────


def new_dream_id() -> str:
    """Generate a fresh dream-session id. ULID-based, time-sortable."""
    return f"dream-{ULID()}"


def cycle_task_id_for(dream_id: str, cycle_number: int) -> str:
    """Stable cycle continuation id derived from the dream id.

    Example: dream_id='dream-01J9...XYZ' cycle=3 → 'cycle-01J9XYZ-003'

    We keep ULID's natural ordering by using the *suffix* of the dream id
    (last 7 chars) so ``ls cycle-*`` sorts cycles within a dream together.
    """
    short = dream_id.split("-", 1)[-1][-7:].lower()
    return f"cycle-{short}-{cycle_number:03d}"


# ─── Store ──────────────────────────────────────────────────────────────────


class DreamStore:
    """Filesystem-backed dream-session registry.

    v0.2.13 added fcntl-backed locking on the dream YAML — see
    ``DreamStore.lock()`` and ``DreamStore.update()``. The per-cycle
    continuation has its own fcntl lock for step-level work, and the
    dream lock guards the dream record itself (cycles list, status,
    file counts) against the rare two-runner race.

    Locking is FILE-SCOPED on a sibling .lock file. We don't lock the
    YAML itself because YAML readers shouldn't see locked files (and
    OSes vary on advisory-vs-mandatory semantics). The convention is:

        <dream_id>.yaml          — the data file
        <dream_id>.yaml.lock     — the lock file (fcntl flock'd)

    A dream advancing without holding the lock is a programmer error,
    not a corruption — saves still go through atomically. The lock is
    about ordering, not safety.
    """

    def __init__(self, root: Path, work_root: Path):
        # root = where the YAML lives. work_root = where each dream's files go.
        self.root = Path(root)
        self.work_root = Path(work_root)

    def _path(self, dream_id: str) -> Path:
        if not _is_safe_id(dream_id):
            raise DreamError(f"invalid dream_id: {dream_id!r}")
        return self.root / f"{dream_id}.yaml"

    def _lock_path(self, dream_id: str) -> Path:
        """Where the fcntl lock file lives. Sibling to the YAML."""
        return self._path(dream_id).with_suffix(".yaml.lock")

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)

    def work_dir_for(self, dream_id: str) -> Path:
        return self.work_root / dream_id

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("dream-*.yaml") if p.is_file())

    def list_all(self, *, status: str | None = None) -> list[DreamSession]:
        out: list[DreamSession] = []
        for did in self.list_ids():
            try:
                d = self.get(did)
            except DreamError:
                continue
            if status is None or d.status == status:
                out.append(d)
        return out

    def exists(self, dream_id: str) -> bool:
        return self._path(dream_id).exists()

    def get(self, dream_id: str) -> DreamSession:
        path = self._path(dream_id)
        if not path.exists():
            raise DreamNotFound(dream_id)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise DreamCorrupt(f"YAML parse error in {path}: {e}") from e
        if not isinstance(data, dict):
            raise DreamCorrupt(f"dream {dream_id}: root must be a mapping")
        return _from_yaml(data)

    def save(self, dream: DreamSession) -> None:
        self.ensure_root()
        path = self._path(dream.dream_id)
        dream.updated_at = _utc_now()
        _atomic_write_text(path, yaml.safe_dump(_to_yaml(dream), sort_keys=False))

    @contextlib.contextmanager
    def lock(self, dream_id: str, *, blocking: bool = True, timeout_seconds: float = 30.0):
        """fcntl-backed exclusive lock on a dream YAML.

        Yields the loaded DreamSession; mutations to the yielded object
        are persisted on context exit (clean exit only — exceptions
        propagate without saving). Lock file is auto-created if missing.

        v0.2.13.
        """
        import fcntl
        import time
        if not self.exists(dream_id):
            raise DreamNotFound(dream_id)
        self.ensure_root()
        lock_path = self._lock_path(dream_id)
        lock_path.touch(exist_ok=True)
        # Open in read-write so flock semantics work uniformly on Linux/macOS.
        f = lock_path.open("r+")
        try:
            mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            if blocking and timeout_seconds:
                # Manual timeout loop; OSError from LOCK_NB is "held by
                # someone else." Sleep and retry until the deadline.
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
                    raise DreamLocked(
                        f"could not acquire lock on dream {dream_id} "
                        f"within {timeout_seconds}s"
                    )
            else:
                try:
                    fcntl.flock(f.fileno(), mode)
                except BlockingIOError as e:
                    raise DreamLocked(
                        f"dream {dream_id} is locked"
                    ) from e

            dream = self.get(dream_id)
            yield dream
            self.save(dream)
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            f.close()

    def create(
        self,
        *,
        goal: str,
        caps: DreamCaps | None = None,
        notes: str = "",
        dream_id: str | None = None,
    ) -> DreamSession:
        """Create a new dream-session.

        ``dream_id=None`` mints a fresh ULID-prefixed id. Pre-supplying an
        id is a test hook — never collide with an existing one (raises
        FileExistsError).
        """
        self.ensure_root()
        did = dream_id or new_dream_id()
        path = self._path(did)
        if path.exists():
            raise FileExistsError(f"dream {did} already exists at {path}")

        work = self.work_dir_for(did)
        work.mkdir(parents=True, exist_ok=True)

        dream = DreamSession(
            dream_id=did,
            goal=goal,
            caps=caps or DreamCaps(),
            work_dir=str(work),
            notes=notes,
        )
        self.save(dream)
        return dream

    def delete(self, dream_id: str, *, delete_work_dir: bool = False) -> bool:
        """Remove the dream YAML. Optionally remove the entire work_dir.

        Default keeps the work_dir intact — a deleted dream's *files* are
        usually what the operator wants to keep. Pass delete_work_dir=True
        to nuke the per-cycle source code too.
        """
        path = self._path(dream_id)
        existed = path.exists()
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        if delete_work_dir:
            work = self.work_dir_for(dream_id)
            if work.exists():
                import shutil
                shutil.rmtree(work, ignore_errors=True)
        return existed


def _is_safe_id(dream_id: str) -> bool:
    if not dream_id:
        return False
    return all(c.isalnum() or c in "-_." for c in dream_id)


# ─── Serialization ──────────────────────────────────────────────────────────


def _to_yaml(d: DreamSession) -> dict:
    return {
        "dream_id": d.dream_id,
        "goal": d.goal,
        "status": d.status,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        "caps": {
            "max_files": d.caps.max_files,
            "max_cycles": d.caps.max_cycles,
            "max_seconds": d.caps.max_seconds,
        },
        "cycles_completed": d.cycles_completed,
        "files_written": d.files_written,
        "elapsed_seconds": d.elapsed_seconds,
        "current_cycle_task_id": d.current_cycle_task_id,
        "work_dir": d.work_dir,
        "notes": d.notes,
        "projects": [asdict(p) for p in d.projects],
        "cycles": [asdict(c) for c in d.cycles],
    }


def _from_yaml(data: dict) -> DreamSession:
    try:
        dream_id = str(data["dream_id"])
        goal = str(data["goal"])
    except KeyError as e:
        raise DreamCorrupt(f"missing required field: {e.args[0]}") from None
    status = str(data.get("status", "active"))
    if status not in _VALID_DREAM_STATUSES:
        raise DreamCorrupt(f"invalid status: {status!r}")

    raw_caps = data.get("caps") or {}
    caps = DreamCaps(
        max_files=_int_or_none(raw_caps.get("max_files")),
        max_cycles=_int_or_none(raw_caps.get("max_cycles")),
        max_seconds=_float_or_none(raw_caps.get("max_seconds")),
    )

    raw_cycles = data.get("cycles") or []
    if not isinstance(raw_cycles, list):
        raise DreamCorrupt("'cycles' must be a list")
    cycles: list[CycleEntry] = []
    for rc in raw_cycles:
        if not isinstance(rc, dict):
            continue
        cycles.append(CycleEntry(
            cycle_number=int(rc.get("cycle_number", 0)),
            task_id=str(rc.get("task_id", "")),
            started_at=str(rc.get("started_at", "")),
            ended_at=rc.get("ended_at"),
            status=str(rc.get("status", "in_progress")),
            cycle_dir=str(rc.get("cycle_dir", "")),
            title=str(rc.get("title", "")),
            files_written=int(rc.get("files_written", 0)),
            elapsed_seconds=float(rc.get("elapsed_seconds", 0.0)),
            notes=str(rc.get("notes", "")),
            # v0.2.13 fields — default 0 for old YAML files (backward compat)
            atoms_written=int(rc.get("atoms_written", 0)),
            quarantined_count=int(rc.get("quarantined_count", 0)),
        ))

    raw_projects = data.get("projects") or []
    if not isinstance(raw_projects, list):
        raise DreamCorrupt("'projects' must be a list")
    projects = [
        ProjectRef(
            name=str(rp.get("name", "")),
            root=str(rp.get("root", "")),
            last_seen_snapshot_at=str(rp.get("last_seen_snapshot_at", "")),
        )
        for rp in raw_projects if isinstance(rp, dict)
    ]

    return DreamSession(
        dream_id=dream_id,
        goal=goal,
        caps=caps,
        status=status,  # type: ignore[arg-type]
        created_at=str(data.get("created_at") or _utc_now()),
        updated_at=str(data.get("updated_at") or _utc_now()),
        cycles_completed=int(data.get("cycles_completed", 0)),
        files_written=int(data.get("files_written", 0)),
        elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
        current_cycle_task_id=data.get("current_cycle_task_id"),
        cycles=cycles,
        projects=projects,
        work_dir=str(data.get("work_dir") or ""),
        notes=str(data.get("notes") or ""),
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
    """Atomic file write — same shape as continuation._atomic_write_text."""
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


def count_files_under(root: Path) -> int:
    """Count regular files under ``root``, recursive. Used for caps.

    Cheap walk — no hashing, no stat'ing for size. Counts what's there
    *now*, regardless of which cycle wrote each file. Symlinks are not
    followed (treated as files-not-counted). Skips ``.git`` and any
    ``quarantine`` subdirectory so failed files don't inflate the cap
    accounting (v0.2.13).
    """
    if not root.exists():
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        parts = dirpath.split(os.sep)
        if ".git" in parts or "quarantine" in parts:
            continue
        # Prune skipped dirs in-place so os.walk doesn't recurse into them.
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


def count_files_in_cycle(cycle_dir: Path) -> int:
    """Count files in ONE cycle dir. Same semantics as count_files_under
    but cheaper to call repeatedly because the dir is small.

    The dream-runner uses this for incremental updates (`old_total +
    cycle_count` instead of re-walking the entire work_root). v0.2.13.
    """
    return count_files_under(cycle_dir)


__all__ = [
    "CycleEntry",
    "DreamCaps",
    "DreamCorrupt",
    "DreamError",
    "DreamExhausted",
    "DreamLocked",
    "DreamNotFound",
    "DreamSession",
    "DreamStore",
    "HARD_CAP_CYCLES",
    "ProjectRef",
    "count_files_in_cycle",
    "count_files_under",
    "cycle_task_id_for",
    "new_dream_id",
]
