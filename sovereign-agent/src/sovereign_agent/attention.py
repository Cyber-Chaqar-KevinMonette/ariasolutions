"""attention — her observable attention queue: who she's serving, in order.

Kevin's policy, encoded:
  • **bot-immediate** (priority 0) — a bot that must fire NOW (an alert
    delivery, an immediate report). Bots that are merely *waiting* (next
    poll in 30 min) consume nothing — the daemon sleeps between due polls,
    so idle bot time is never wasted and never blocks anyone.
  • **customer** (priority 1) — customers come BEFORE Kevin's work.
  • **kevin** (priority 2) — his work fills all remaining attention.

The genuinely shared resource is her language model (the bots don't use
one). This queue sits in front of it: entries are ordered by (priority,
arrival), every entry can ask "what's my position?", and the whole queue is
visible in the ⏱ Timers window — so nobody wonders where they stand.

Cross-process by design (the ask-lane lives in the Discord bot process, the
cockpit in another): a small JSON file with atomic writes, and every
read-modify-write (enqueue/done) holds an OS file lock so two processes can
never lose each other's entries. Crash-safe twice over: the lock releases
with the process, and an entry older than its TTL is swept automatically,
so a dead process can never wedge the line.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "LANE_BOT", "LANE_CUSTOMER", "LANE_KEVIN",
    "AttentionQueue", "QueueEntry",
]

LANE_BOT = "bot-immediate"
LANE_CUSTOMER = "customer"
LANE_KEVIN = "kevin"
_PRIORITY = {LANE_BOT: 0, LANE_CUSTOMER: 1, LANE_KEVIN: 2}

ENTRY_TTL_S = 120.0          # a crashed holder's entry sweeps itself away
_AVG_SERVE_S = 15.0          # honest rough ETA per entry ahead


@dataclass(frozen=True)
class QueueEntry:
    entry_id: str
    lane: str
    label: str               # short public label ("customer u42", "kevin: work")
    ts: float

    @property
    def priority(self) -> int:
        return _PRIORITY.get(self.lane, 3)


class AttentionQueue:
    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        self._path = Path(data_dir) / "attention" / "queue.json"

    @contextlib.contextmanager
    def _locked(self):
        """Exclusive cross-process lock for read-modify-write. Held only for
        the microseconds a mutation takes; auto-released if the holder dies.
        Never raises — on any locking trouble the mutation proceeds unlocked
        (same behavior as before this guard existed)."""
        fh = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self._path.parent / ".lock", "w", encoding="utf-8")
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except Exception:  # noqa: BLE001
            pass
        try:
            yield
        finally:
            if fh is not None:
                with contextlib.suppress(Exception):
                    fh.close()          # closing releases the flock

    # ── file plumbing (atomic, crash-safe) ──
    def _load(self, now: float) -> list[QueueEntry]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            raw = []
        out: list[QueueEntry] = []
        for e in raw if isinstance(raw, list) else []:
            try:
                entry = QueueEntry(str(e["entry_id"]), str(e["lane"]),
                                   str(e.get("label", ""))[:48], float(e["ts"]))
            except Exception:  # noqa: BLE001
                continue
            if now - entry.ts <= ENTRY_TTL_S:   # sweep stale/crashed holders
                out.append(entry)
        out.sort(key=lambda e: (e.priority, e.ts))
        return out

    def _save(self, entries: list[QueueEntry]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(
                [{"entry_id": e.entry_id, "lane": e.lane, "label": e.label,
                  "ts": e.ts} for e in entries], ensure_ascii=False),
                encoding="utf-8")
            with open(tmp, "r+", encoding="utf-8") as fh:
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(self._path)
        except Exception:  # noqa: BLE001
            pass

    # ── the API ──
    def enqueue(self, lane: str, label: str, *, now: float | None = None) -> str:
        now = time.time() if now is None else now
        entry = QueueEntry(uuid.uuid4().hex[:8], lane, label[:48], now)
        with self._locked():
            entries = self._load(now)
            entries.append(entry)
            entries.sort(key=lambda e: (e.priority, e.ts))
            self._save(entries)
        return entry.entry_id

    def done(self, entry_id: str, *, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._locked():
            entries = [e for e in self._load(now) if e.entry_id != entry_id]
            self._save(entries)

    def position(self, entry_id: str, *, now: float | None = None) -> int | None:
        """1-based place in line (1 = being served next/now)."""
        now = time.time() if now is None else now
        for i, e in enumerate(self._load(now), 1):
            if e.entry_id == entry_id:
                return i
        return None

    def snapshot(self, *, now: float | None = None) -> list[QueueEntry]:
        now = time.time() if now is None else now
        return self._load(now)

    def eta_s(self, entry_id: str, *, now: float | None = None) -> float | None:
        pos = self.position(entry_id, now=now)
        return None if pos is None else max(0.0, (pos - 1) * _AVG_SERVE_S)

    def render(self, *, now: float | None = None) -> str:
        entries = self.snapshot(now=now)
        if not entries:
            return "🎯 Attention queue: empty — she's all yours."
        icons = {LANE_BOT: "🤖", LANE_CUSTOMER: "🛒", LANE_KEVIN: "👑"}
        lines = [f"🎯 Attention queue ({len(entries)} waiting — bots-immediate "
                 f"→ customers → Kevin):"]
        for i, e in enumerate(entries, 1):
            lines.append(f"  {i}. {icons.get(e.lane, '•')} {e.label} "
                         f"[dim]({e.lane})[/dim]")
        return "\n".join(lines)
