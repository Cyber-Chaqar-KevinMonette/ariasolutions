"""store.py — durable, crash-safe apply-queue + quarantine registry.

Kevin's flow: in the cockpit he *selects* which staged modules to apply (he can't
apply while the cockpit runs — that would mutate live ``src/`` beneath it). The
selection is written here as a durable, dependency-sequenced queue. He closes the
cockpit; ``scripts/apply_queue_run.sh`` drains the queue through
``scripts/safe_apply.sh`` (guarded + auto-rollback). On success an item is removed
from the active queue; on rollback it is routed to **quarantine** for evaluation
until fixed — never lost.

Two surfaces, both file-backed (no DB, no daemon):

  • ApplyQueueStore   — ``<data>/apply_queue/queue.ndjson``  (append-only event log,
                        source of truth) + ``queue.current.json`` (the live active
                        view, rewritten on every mutation so Kevin watches it shrink).
  • QuarantineRegistry — ``<data>/quarantine/<slug>.json``   (one record per failure).

The append-only log mirrors ``rollback.RollbackStore``'s atomic-write discipline:
write a ``.tmp`` then ``os.replace`` so a crash never leaves a half-written record.
Propose-only: this module *records intent and outcome*; the human (via the sequencer
script, cockpit stopped) is the only actor that mutates live ``src/``.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from sovereign_agent.config import SETTINGS

QueueStatus = Literal["queued", "applying", "applied", "quarantined"]
_ACTIVE: tuple[QueueStatus, ...] = ("queued", "applying")
_TERMINAL: tuple[QueueStatus, ...] = ("applied", "quarantined")

# Dependency order — mirrors PRIORITY[] in scripts/apply_queue.sh. Modules whose
# apply patches the tool/sentinel registration chain must land first, in chain
# order; everything else is independent and sequenced alphabetically after.
PRIORITY: tuple[str, ...] = (
    "aria-own-mind", "aria-immune-system", "aria-constitution",
    "aria-tribunal", "aria-frugality", "aria-foresight", "aria-godtier-scanner",
    "aria-path-sentinel",  # the gate (D) goes early so it protects later applies
    "aria-senses", "aria-autonomy-session",
    "aria-nonclassical-godtier", "aria-nonclassical-supreme",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _priority_rank(slug: str) -> tuple[int, str]:
    """Sort key: PRIORITY members in chain order first, then alphabetical."""
    try:
        return (PRIORITY.index(slug), "")
    except ValueError:
        return (len(PRIORITY), slug)


# ── queue ──────────────────────────────────────────────────────────────────


@dataclass
class QueueItem:
    slug: str                       # canonical "aria-<name>" module folder
    seq: int                        # 1-based apply order (dependency-sequenced)
    status: QueueStatus = "queued"
    requested_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    depends_on: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class ApplyQueueStore:
    """Append-only, crash-safe apply queue. State = reduction of the event log."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (SETTINGS.paths.data_dir / "apply_queue")
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "queue.ndjson"          # append-only source of truth
        self.current = self.root / "queue.current.json"  # live active view

    # — write path —

    def _append(self, item: QueueItem) -> None:
        """Append one event record atomically (never corrupts the log on crash)."""
        line = json.dumps(item.as_dict(), separators=(",", ":")) + "\n"
        # Append is atomic for <PIPE_BUF writes; we also fsync to survive a crash.
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self._render_current()

    def enqueue(self, slugs: list[str], *, note: str = "") -> list[QueueItem]:
        """Add modules to the queue in dependency order; returns the new items.

        Already-active modules are skipped (idempotent — selecting twice in the
        cockpit never double-queues). Sequence numbers are assigned across the
        whole resulting active set so the order is always globally coherent.
        """
        active = {it.slug for it in self.active()}
        fresh = [s for s in dict.fromkeys(slugs) if s not in active]  # dedupe, keep order
        added: list[QueueItem] = []
        for slug in fresh:
            item = QueueItem(slug=slug, seq=0, note=note)
            self._append(item)
            added.append(item)
        self._resequence()
        return self.active() if added else []

    def mark(self, slug: str, status: QueueStatus, *, note: str = "") -> QueueItem:
        """Record a status transition for a module (queued→applying→applied/quarantined)."""
        cur = self._state().get(slug)
        seq = cur.seq if cur else 0
        depends = cur.depends_on if cur else []
        requested = cur.requested_at if cur else _now()
        item = QueueItem(
            slug=slug, seq=seq, status=status, requested_at=requested,
            updated_at=_now(), depends_on=depends, note=note or (cur.note if cur else ""),
        )
        self._append(item)
        return item

    def _resequence(self) -> None:
        """Reassign seq across active items in dependency order, persisting the change."""
        items = sorted(self.active(), key=lambda it: _priority_rank(it.slug))
        for i, it in enumerate(items, start=1):
            if it.seq != i:
                it.seq = i
                it.updated_at = _now()
                # append a re-seq event (status unchanged) so the log stays the truth
                line = json.dumps(it.as_dict(), separators=(",", ":")) + "\n"
                with open(self.log, "a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
        self._render_current()

    # — read path —

    def _state(self) -> dict[str, QueueItem]:
        """Reduce the append-only log: last record per slug wins."""
        state: dict[str, QueueItem] = {}
        if not self.log.exists():
            return state
        for raw in self.log.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
                state[d["slug"]] = QueueItem(**d)
            except (json.JSONDecodeError, TypeError, KeyError):
                continue  # corrupt line; skip (never crash the queue on bad data)
        return state

    def active(self) -> list[QueueItem]:
        """Modules still to apply (queued/applying), in seq order."""
        items = [it for it in self._state().values() if it.status in _ACTIVE]
        return sorted(items, key=lambda it: (it.seq if it.seq else 9999, _priority_rank(it.slug)))

    def all_items(self) -> list[QueueItem]:
        return sorted(self._state().values(), key=lambda it: _priority_rank(it.slug))

    def pending_slugs(self) -> list[str]:
        """The sequencer reads this — active modules in apply order."""
        return [it.slug for it in self.active()]

    def _render_current(self) -> None:
        """Rewrite the human-facing active view atomically (Kevin watches it shrink)."""
        payload = {
            "generated_at": _now(),
            "active": [it.as_dict() for it in self.active()],
            "count": len(self.active()),
        }
        tmp = self.current.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.current)

    def clear(self) -> None:
        """Reset the queue (audit log archived, not deleted)."""
        if self.log.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self.log.rename(self.root / f"queue.{stamp}.ndjson.archive")
        self._render_current()


# ── quarantine ─────────────────────────────────────────────────────────────


@dataclass
class QuarantineRecord:
    slug: str
    failed_at: str
    reason: str
    snapshot_path: str = ""
    gate_verdict: str = ""
    status: Literal["quarantined", "cleared"] = "quarantined"

    def as_dict(self) -> dict:
        return asdict(self)


class QuarantineRegistry:
    """One JSON file per quarantined module — reviewable, not lost.

    A module whose apply rolled back lands here for evaluation until fixed
    (Kevin's 4 broken modules + any new failures). Atomic writes mirror
    ``rollback.RollbackStore``.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (SETTINGS.paths.data_dir / "quarantine")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        if "/" in slug or ".." in slug:
            raise ValueError(f"invalid slug: {slug!r}")
        return self.root / f"{slug}.json"

    def quarantine(self, slug: str, reason: str, *, snapshot_path: str = "",
                   gate_verdict: str = "") -> QuarantineRecord:
        rec = QuarantineRecord(
            slug=slug, failed_at=_now(), reason=reason,
            snapshot_path=snapshot_path, gate_verdict=gate_verdict,
        )
        target = self._path(slug)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec.as_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return rec

    def show(self, slug: str) -> QuarantineRecord | None:
        p = self._path(slug)
        if not p.exists():
            return None
        try:
            return QuarantineRecord(**json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return None

    def list(self) -> list[QuarantineRecord]:
        out: list[QuarantineRecord] = []
        for p in sorted(self.root.glob("*.json")):
            try:
                out.append(QuarantineRecord(**json.loads(p.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def clear(self, slug: str) -> bool:
        """Mark a quarantine record cleared (fixed). Returns True if it existed."""
        rec = self.show(slug)
        if rec is None:
            return False
        rec.status = "cleared"
        target = self._path(slug)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec.as_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return True

    def active(self) -> list[QuarantineRecord]:
        return [r for r in self.list() if r.status == "quarantined"]
