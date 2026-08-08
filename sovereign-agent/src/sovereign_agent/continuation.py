"""
╔══════════════════════════════════════════════════════════════════════════╗
║  continuation.py — Re-trigger architecture state                         ║
║  Architecture §13 (new in v0.2.5)                                        ║
╚══════════════════════════════════════════════════════════════════════════╝

A continuation file is durable, replayable task state. The pattern:

    plan ──► continuation.yaml (N steps, status=pending)
                    │
                    ▼
    sovereign continue <id>  (read state → run ONE step → write state → exit)
                    │
                    ▼  (driver loop or systemd timer)
    repeat until cont.status == "done" | "poisoned" | HALT

The model never sees the full plan — each invocation gets one tiny step as
its goal. Memory and lessons accumulate in atoms.db across invocations.
The continuation file is the only carrier of progress between invocations.

Concurrency invariants:

  ◊ Exactly one ``sovereign continue <id>`` runs against a continuation at
    a time. Enforced by an exclusive file lock acquired for the entire
    invocation.
  ◊ A second concurrent invocation fails fast with ContinuationLocked, not
    silent data loss.
  ◊ Crashed prior invocations leave the file in a recoverable state because
    every write is via atomic-replace (write tmp + fsync + rename).
  ◊ The lock file is independent of the data file; it survives schema
    changes and never holds stale data.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

import yaml
from ulid import ULID


# Status enum kept as Literal type — no runtime enum needed; YAML values
# are the canonical form. Adding a status means adding to this Literal AND
# to the validator below.
#
# v0.2.12+ — "paused" is a soft halt at the continuation level. The runner
# refuses to advance a paused continuation; ``sov resume <id>`` flips it
# back to in_progress. Distinct from PROTOCOL-ZERO (system-wide HALT) and
# from the "halted" terminal status (which is not currently produced by
# any code path but is preserved for backward compat).
ContinuationStatus = Literal["planned", "in_progress", "done", "poisoned", "halted", "paused"]
StepStatus = Literal["pending", "done", "poisoned", "skipped"]

_VALID_CONT_STATUSES: frozenset[str] = frozenset(
    {"planned", "in_progress", "done", "poisoned", "halted", "paused"}
)
_VALID_STEP_STATUSES: frozenset[str] = frozenset(
    {"pending", "done", "poisoned", "skipped"}
)


class ContinuationError(Exception):
    """Base class for continuation errors."""


class ContinuationLocked(ContinuationError):
    """Another process holds the lock for this continuation."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"continuation {task_id} is locked by another process")


class ContinuationNotFound(ContinuationError):
    """No continuation file exists for the given task_id."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"continuation {task_id} not found")


class ContinuationCorrupt(ContinuationError):
    """The continuation file is malformed or fails validation."""


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def format_elapsed(seconds: float | None) -> str:
    """Format a duration in seconds as a human-readable string.

    Used for reports/observability — shows hours/minutes/seconds at a glance
    without the operator having to do mental arithmetic. v0.2.7+.

    Examples:
        0.42   → "0.42s"
        12.7   → "12.70s"
        90     → "1m 30s"
        3725   → "1h 2m 5s"
        None   → "—"
    """
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes_total = int(seconds // 60)
    secs_remainder = int(seconds - minutes_total * 60)
    if minutes_total < 60:
        return f"{minutes_total}m {secs_remainder}s"
    hours = minutes_total // 60
    minutes_remainder = minutes_total - hours * 60
    return f"{hours}h {minutes_remainder}m {secs_remainder}s"


@dataclass
class Step:
    """One atomic unit of work within a continuation.

    A step is what the agent loop runs as a single ONESHOT task. It must be
    small enough to complete within the per-step budget (default 5 iter,
    120s wall) so the model context stays bounded across the whole task.

    The ``required_model`` field declares which model class this step needs
    loaded ('orchestrator' | 'vision' | 'coder' | 'fast'). The
    ``ContinueModeRunner`` and ``drain-by-model`` orchestrator use this to
    batch steps with the same model affinity, so each model loads once
    rather than per-step. Default is 'orchestrator' (the v0.2.5 behavior),
    so any v0.2.5 continuation file remains valid in v0.2.6.

    The ``elapsed_seconds`` field (v0.2.7+) records wall-clock time spent
    actually executing this step. Used for reporting and observability —
    surfaced in ``continuations show`` and the event log. None means the
    step has not completed.
    """

    id: int
    kind: str                                  # planner-defined: "inventory_file", "distill_file", ...
    args: dict = field(default_factory=dict)   # planner-defined
    status: StepStatus = "pending"
    result: str | None = None                  # truncated; full result is in the event log
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    iterations: int = 0
    tokens: int = 0
    required_model: str = "orchestrator"       # model affinity for batching (v0.2.6+)
    elapsed_seconds: float | None = None       # wall-clock time spent on this step (v0.2.7+)
    # v0.2.11+ — VRAM trace, only populated for model-invoking steps.
    # None on no-GPU systems or pure-Python steps.
    vram_before_mb: int | None = None
    vram_peak_mb: int | None = None
    vram_after_mb: int | None = None


@dataclass
class Continuation:
    """A planned task with replayable per-step state.

    Read fields freely. Mutations made inside ``ContinuationStore.lock(...)``
    are persisted on context exit; mutations made outside are NOT persisted.
    """

    task_id: str
    goal: str
    planner: str
    planner_args: dict = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    status: ContinuationStatus = "planned"
    created_at: str = field(default_factory=_utc_now_rfc3339)
    updated_at: str = field(default_factory=_utc_now_rfc3339)
    output_path: str | None = None             # optional aggregation target (planner's choice)
    notes: str = ""

    @property
    def cursor(self) -> int:
        """Index of the next pending step, or len(steps) if none remain."""
        return next(
            (i for i, s in enumerate(self.steps) if s.status == "pending"),
            len(self.steps),
        )

    @property
    def progress(self) -> tuple[int, int]:
        """(completed, total). 'completed' counts done | poisoned | skipped."""
        total = len(self.steps)
        done = sum(1 for s in self.steps if s.status != "pending")
        return done, total

    def next_pending(self) -> Step | None:
        """The next step to execute. None if drained."""
        return next((s for s in self.steps if s.status == "pending"), None)

    def next_pending_for_model(self, model: str) -> Step | None:
        """Next pending step requiring the given model class. None if none.

        Used by ``--model-filter`` runs and ``drain-by-model`` to batch
        steps by model affinity. ``model`` matches ``Step.required_model``
        exactly — case-sensitive.
        """
        return next(
            (s for s in self.steps if s.status == "pending" and s.required_model == model),
            None,
        )

    def models_needed(self) -> list[str]:
        """Distinct ``required_model`` values across all pending steps.

        Returned in stable order: orchestrator first (most common, fastest
        to start), then alphabetically. ``drain-by-model`` uses this order
        as its phase plan unless the operator overrides.
        """
        pending_models = {s.required_model for s in self.steps if s.status == "pending"}
        if not pending_models:
            return []
        order: list[str] = []
        if "orchestrator" in pending_models:
            order.append("orchestrator")
            pending_models.discard("orchestrator")
        order.extend(sorted(pending_models))
        return order

    def progress_by_model(self) -> dict[str, tuple[int, int]]:
        """Per-model (completed, total) tuples, summed across all steps.

        Returned as ``{model_name: (done, total)}``. Useful for status
        displays — shows how each phase is progressing without hiding
        per-model failure clusters.
        """
        out: dict[str, list[int]] = {}
        for s in self.steps:
            slot = out.setdefault(s.required_model, [0, 0])
            slot[1] += 1
            if s.status != "pending":
                slot[0] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    @property
    def total_elapsed_seconds(self) -> float:
        """Sum of elapsed_seconds across all completed steps. v0.2.7+."""
        return sum((s.elapsed_seconds or 0.0) for s in self.steps)

    def elapsed_by_model(self) -> dict[str, float]:
        """Total elapsed time grouped by required_model. v0.2.7+.

        Useful for reports: 'Phase orchestrator took 1h 12m, phase vision
        took 45m, phase coder took 18m'.
        """
        out: dict[str, float] = {}
        for s in self.steps:
            if s.elapsed_seconds is not None:
                out[s.required_model] = out.get(s.required_model, 0.0) + s.elapsed_seconds
        return out

    def is_drained(self) -> bool:
        """All steps reached a terminal status (no pending remaining)."""
        return all(s.status != "pending" for s in self.steps)

    def update_status_from_steps(self) -> None:
        """Recompute self.status from per-step statuses.

        Drained + any poison → poisoned. Drained + all done/skipped → done.
        Anything else → in_progress (caller is responsible for halted).

        v0.2.12+ — ``paused`` is preserved across recomputation. Pausing is
        an operator-level intent that survives any number of step writes.
        Only ``sov resume`` clears it. Drained continuations always settle
        to done/poisoned regardless — pause has no meaning when no steps
        remain.
        """
        if not self.steps:
            self.status = "planned"
            return
        # Preserve the paused flag while there's still work to do.
        if self.status == "paused" and not self.is_drained():
            return
        if not self.is_drained():
            self.status = "in_progress"
            return
        if any(s.status == "poisoned" for s in self.steps):
            self.status = "poisoned"
        else:
            self.status = "done"


# ─── Serialization ──────────────────────────────────────────────────────────


def _to_yaml_dict(cont: Continuation) -> dict:
    """Stable, human-readable YAML projection."""
    return {
        "task_id": cont.task_id,
        "goal": cont.goal,
        "planner": cont.planner,
        "planner_args": cont.planner_args,
        "status": cont.status,
        "created_at": cont.created_at,
        "updated_at": cont.updated_at,
        "output_path": cont.output_path,
        "notes": cont.notes,
        "steps": [asdict(s) for s in cont.steps],
    }


def _from_yaml_dict(d: dict) -> Continuation:
    """Strict deserialization with explicit failure on malformed input.

    Unknown fields are dropped silently (forward compat). Required fields
    being missing or wrong-typed raises ContinuationCorrupt.
    """
    if not isinstance(d, dict):
        raise ContinuationCorrupt("continuation root must be a mapping")
    try:
        task_id = str(d["task_id"])
        goal = str(d["goal"])
        planner = str(d["planner"])
    except KeyError as e:
        raise ContinuationCorrupt(f"missing required field: {e.args[0]}") from None

    status = str(d.get("status", "planned"))
    if status not in _VALID_CONT_STATUSES:
        raise ContinuationCorrupt(f"invalid status: {status!r}")

    raw_steps = d.get("steps") or []
    if not isinstance(raw_steps, list):
        raise ContinuationCorrupt("'steps' must be a list")

    steps: list[Step] = []
    for i, rs in enumerate(raw_steps):
        if not isinstance(rs, dict):
            raise ContinuationCorrupt(f"step {i} is not a mapping")
        s_status = str(rs.get("status", "pending"))
        if s_status not in _VALID_STEP_STATUSES:
            raise ContinuationCorrupt(f"step {i} has invalid status: {s_status!r}")
        steps.append(
            Step(
                id=int(rs.get("id", i)),
                kind=str(rs.get("kind", "")),
                args=dict(rs.get("args") or {}),
                status=s_status,  # type: ignore[arg-type]
                result=rs.get("result"),
                error=rs.get("error"),
                started_at=rs.get("started_at"),
                completed_at=rs.get("completed_at"),
                iterations=int(rs.get("iterations", 0)),
                tokens=int(rs.get("tokens", 0)),
                required_model=str(rs.get("required_model") or "orchestrator"),
                elapsed_seconds=(
                    float(rs["elapsed_seconds"])
                    if rs.get("elapsed_seconds") is not None
                    else None
                ),
                # v0.2.11+ — VRAM trace fields. Optional; default None.
                vram_before_mb=(
                    int(rs["vram_before_mb"])
                    if rs.get("vram_before_mb") is not None
                    else None
                ),
                vram_peak_mb=(
                    int(rs["vram_peak_mb"])
                    if rs.get("vram_peak_mb") is not None
                    else None
                ),
                vram_after_mb=(
                    int(rs["vram_after_mb"])
                    if rs.get("vram_after_mb") is not None
                    else None
                ),
            )
        )

    return Continuation(
        task_id=task_id,
        goal=goal,
        planner=planner,
        planner_args=dict(d.get("planner_args") or {}),
        steps=steps,
        status=status,  # type: ignore[arg-type]
        created_at=str(d.get("created_at") or _utc_now_rfc3339()),
        updated_at=str(d.get("updated_at") or _utc_now_rfc3339()),
        output_path=d.get("output_path"),
        notes=str(d.get("notes") or ""),
    )


# ─── Atomic file writes ─────────────────────────────────────────────────────


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically: write to sibling tmpfile, fsync, rename.

    On Linux + ext4/xfs/btrfs, ``rename(2)`` is atomic for files on the same
    filesystem. If the process crashes between fsync and rename, the old
    file remains intact. If it crashes during rename, the rename either
    completed or didn't — never half.
    """
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


# ─── The store ──────────────────────────────────────────────────────────────


class ContinuationStore:
    """Filesystem-backed continuation registry under a root directory.

    Layout:
        <root>/
          <task_id>.yaml          # the data file (atomic-replaced)
          <task_id>.yaml.lock     # the lock file (fcntl.flock target)

    Locks are advisory (fcntl.flock) — only respected by participating
    processes. That's fine: every code path that mutates a continuation
    goes through this class.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    # ── path helpers ────────────────────────────────────────────────────

    def _data_path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.yaml"

    def _lock_path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.yaml.lock"

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    # ── read paths (no lock — eventual-consistent reads) ────────────────

    def get(self, task_id: str) -> Continuation:
        """Read a continuation. Raises ContinuationNotFound or *Corrupt."""
        path = self._data_path(task_id)
        if not path.exists():
            raise ContinuationNotFound(task_id)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ContinuationCorrupt(f"YAML parse error in {path}: {e}") from e
        if data is None:
            raise ContinuationCorrupt(f"empty continuation file: {path}")
        return _from_yaml_dict(data)

    def list_ids(self) -> list[str]:
        """Return all known task_ids. Sorted ascending (ULIDs are time-ordered)."""
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.yaml") if p.is_file())

    def list_all(self, *, status: str | None = None) -> list[Continuation]:
        """Read every continuation. Optionally filter by status.

        Corrupt files are skipped silently (logged in the caller's choice
        of channel). For a strict read use ``get()`` per id.
        """
        out: list[Continuation] = []
        for tid in self.list_ids():
            try:
                cont = self.get(tid)
            except ContinuationError:
                continue
            if status is None or cont.status == status:
                out.append(cont)
        return out

    # ── write paths (require lock) ──────────────────────────────────────

    def create(
        self,
        *,
        goal: str,
        planner: str,
        planner_args: dict,
        steps: list[Step],
        output_path: str | None = None,
        task_id: str | None = None,
        notes: str = "",
    ) -> Continuation:
        """Create a new continuation. Returns the created Continuation.

        ``task_id`` defaults to a fresh ULID. If a continuation with the
        same id already exists, raises FileExistsError.
        """
        self.ensure_root()
        tid = task_id or f"cont-{ULID()}"
        path = self._data_path(tid)
        if path.exists():
            raise FileExistsError(f"continuation {tid} already exists at {path}")

        cont = Continuation(
            task_id=tid,
            goal=goal,
            planner=planner,
            planner_args=dict(planner_args),
            steps=list(steps),
            status="planned" if steps else "done",
            output_path=output_path,
            notes=notes,
        )
        # Initialize step IDs if planner left them at default 0
        for i, step in enumerate(cont.steps):
            if step.id == 0 and i != 0:
                step.id = i
        _atomic_write_text(path, yaml.safe_dump(_to_yaml_dict(cont), sort_keys=False))
        return cont

    @contextlib.contextmanager
    def lock(
        self, task_id: str, *, blocking: bool = False, timeout_seconds: float = 0.0
    ) -> Iterator[Continuation]:
        """Acquire exclusive lock on a continuation for the block duration.

        Read on entry, write on exit (only if the block completes without
        an exception). Two concurrent ``with store.lock(id):`` blocks
        cannot interleave — the second raises ContinuationLocked
        (or blocks if ``blocking=True``).

        ``blocking=True`` with ``timeout_seconds>0`` polls for the lock
        until it becomes available or the timeout elapses; ``timeout_seconds=0``
        with ``blocking=True`` waits indefinitely.

        On exception inside the block, NO write happens — the prior state
        is preserved.
        """
        self.ensure_root()
        path = self._data_path(task_id)
        lockpath = self._lock_path(task_id)
        if not path.exists():
            raise ContinuationNotFound(task_id)

        # Open (or create) the lock file. We never write to it — it exists
        # purely as an flock target. This also means the data file can be
        # atomic-renamed without invalidating the lock.
        lock_fd = os.open(lockpath, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            self._acquire_flock(lock_fd, task_id, blocking, timeout_seconds)
            try:
                cont = self.get(task_id)
                yield cont
                # Persist on clean exit.
                cont.updated_at = _utc_now_rfc3339()
                _atomic_write_text(
                    path, yaml.safe_dump(_to_yaml_dict(cont), sort_keys=False)
                )
            finally:
                # Release before close so other waiters wake immediately.
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

    @staticmethod
    def _acquire_flock(
        lock_fd: int, task_id: str, blocking: bool, timeout_seconds: float
    ) -> None:
        """Acquire LOCK_EX on lock_fd, with optional bounded wait.

        On Linux, fcntl.flock(LOCK_EX | LOCK_NB) returns BlockingIOError
        if the lock is held. We poll (with a small sleep) when the caller
        asked for blocking-with-timeout.
        """
        if not blocking:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                raise ContinuationLocked(task_id) from None

        if timeout_seconds <= 0:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            return

        # Bounded wait: poll at 50ms.
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ContinuationLocked(task_id) from None
                time.sleep(0.05)

    def delete(self, task_id: str) -> bool:
        """Remove the continuation. Returns True if it existed.

        Acquires the lock briefly so we don't race a running ``continue``.
        After removing the data file, the lock file is also removed.
        """
        self.ensure_root()
        path = self._data_path(task_id)
        lockpath = self._lock_path(task_id)
        if not path.exists():
            return False

        # Acquire (non-blocking) to refuse if a runner holds the lock.
        lock_fd = os.open(lockpath, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContinuationLocked(task_id) from None
            try:
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
                with contextlib.suppress(FileNotFoundError):
                    lockpath.unlink()
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return False
            raise
        finally:
            os.close(lock_fd)
        return True
