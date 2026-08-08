"""queue — a durable delivery queue so no alert is ever lost.

The reliability core. Delivery is fallible (Discord hiccups, transient
network); firing inline would drop an alert on the first failure. Instead
every alert becomes a durable `Job`, and a worker drains the queue with the
patterns proven at scale (SQS / Sidekiq / BullMQ lineage), all local:

  • **At-least-once + idempotent** — `enqueue` dedups on a caller key, so the
    same alert never queues twice.
  • **Visibility timeout** — a leased job that isn't completed (worker
    crashed, process killed) is reclaimed after `lease_ttl_s` and retried.
    Nothing is lost to a crash mid-send.
  • **Exponential backoff** — a failed job retries after `base * 2**(n-1)`,
    capped, so a struggling target gets breathing room.
  • **Dead-letter** — after `max_attempts` a job moves to a dead-letter list
    you can inspect (`sov bots queue`) and later requeue — a poison message
    never blocks the queue forever.

Storage: `queue.json` (pending/inflight) + `deadletter.json` per project,
atomic + fsync, corrupt-file-resilient. Volumes here are tiny (a few
alerts/min), so a whole-file rewrite is simplest and crash-safe.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Job", "JobQueue"]

PENDING = "pending"
INFLIGHT = "inflight"


@dataclass
class Job:
    content: str
    key: str = ""                       # idempotency key (dedup on enqueue)
    id: str = ""
    attempts: int = 0
    status: str = PENDING
    next_at: float = 0.0                # earliest time this job may run
    lease_until: float = 0.0            # when an inflight lease expires
    last_error: str = ""
    # panel-d (Kevin, 2026-07-27): an optional rich embed riding beside
    # `content` — additive; every existing job (and every project that
    # never sets one) round-trips through JSON exactly as before.
    embed: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobQueue:
    path_dir: Path
    max_attempts: int = 5
    base_backoff_s: float = 30.0
    max_backoff_s: float = 3600.0
    lease_ttl_s: float = 120.0
    _pending: list[Job] = field(default_factory=list)
    _dead: list[Job] = field(default_factory=list)
    _loaded: bool = False

    # ── paths ──
    def _qpath(self) -> Path:
        Path(self.path_dir).mkdir(parents=True, exist_ok=True)
        return Path(self.path_dir) / "queue.json"

    def _dpath(self) -> Path:
        Path(self.path_dir).mkdir(parents=True, exist_ok=True)
        return Path(self.path_dir) / "deadletter.json"

    # ── persistence ──
    def _load(self) -> None:
        if self._loaded:
            return
        self._pending = _read_jobs(self._qpath())
        self._dead = _read_jobs(self._dpath())
        self._loaded = True

    def _flush(self) -> None:
        _write_jobs(self._qpath(), self._pending)
        _write_jobs(self._dpath(), self._dead)

    # ── operations ──
    def enqueue(self, content: str, *, key: str = "", now: float = 0.0,
               embed: dict[str, Any] | None = None) -> Job | None:
        self._load()
        if key:
            for j in self._pending:
                if j.key == key:
                    return None          # idempotent — already queued
        job = Job(content=content, key=key, id=uuid.uuid4().hex, next_at=now,
                 embed=embed)
        self._pending.append(job)
        self._flush()
        return job

    def reclaim(self, now: float) -> int:
        """Return inflight jobs whose lease expired back to pending."""
        self._load()
        n = 0
        for j in self._pending:
            if j.status == INFLIGHT and now >= j.lease_until:
                j.status = PENDING
                n += 1
        if n:
            self._flush()
        return n

    def lease(self, now: float, limit: int = 10) -> list[Job]:
        """Claim up to `limit` due pending jobs, marking them inflight."""
        self._load()
        self.reclaim(now)
        leased: list[Job] = []
        for j in self._pending:
            if j.status == PENDING and now >= j.next_at:
                j.status = INFLIGHT
                j.lease_until = now + self.lease_ttl_s
                leased.append(j)
                if len(leased) >= limit:
                    break
        if leased:
            self._flush()
        return leased

    def complete(self, job_id: str) -> None:
        self._load()
        before = len(self._pending)
        self._pending = [j for j in self._pending if j.id != job_id]
        if len(self._pending) != before:
            self._flush()

    def fail(self, job_id: str, now: float, error: str = "") -> str:
        """Record a failed attempt: retry with backoff, or dead-letter.
        Returns 'retry' or 'dead'."""
        self._load()
        for j in self._pending:
            if j.id == job_id:
                j.attempts += 1
                j.last_error = error[:200]
                if j.attempts >= self.max_attempts:
                    self._pending.remove(j)
                    j.status = "dead"
                    self._dead.append(j)
                    self._flush()
                    return "dead"
                backoff = min(self.max_backoff_s,
                              self.base_backoff_s * (2 ** (j.attempts - 1)))
                j.status = PENDING
                j.next_at = now + backoff
                j.lease_until = 0.0
                self._flush()
                return "retry"
        return "retry"

    def requeue_dead(self, now: float = 0.0) -> int:
        """Move every dead-letter job back to pending (after you've fixed the
        cause). Resets attempts."""
        self._load()
        n = len(self._dead)
        for j in self._dead:
            j.status = PENDING
            j.attempts = 0
            j.next_at = now
            self._pending.append(j)
        self._dead = []
        if n:
            self._flush()
        return n

    # ── inspection ──
    def pending_count(self) -> int:
        self._load()
        return sum(1 for j in self._pending if j.status == PENDING)

    def inflight_count(self) -> int:
        self._load()
        return sum(1 for j in self._pending if j.status == INFLIGHT)

    def dead_letter(self) -> list[Job]:
        self._load()
        return list(self._dead)


def _read_jobs(path: Path) -> list[Job]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out: list[Job] = []
    known = {f for f in Job(content="x").as_dict()}
    for entry in raw if isinstance(raw, list) else []:
        try:
            out.append(Job(**{k: v for k, v in entry.items() if k in known}))
        except Exception:  # noqa: BLE001
            continue
    return out


def _write_jobs(path: Path, jobs: list[Job]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps([j.as_dict() for j in jobs], indent=2, ensure_ascii=False),
                   encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
