"""
╔══════════════════════════════════════════════════════════════════════════╗
║  clock/timers.py — the Erebo Clock                                         ║
║  v0.2.37 — skeleton drop                                                  ║
║                                                                           ║
║  Aria's first-class time primitive. Timers survive restarts because     ║
║  they live in the same SQLite store as everything else. The clock loop ║
║  is a single-thread poller that fires due timers and dispatches their  ║
║  payloads to a registered handler.                                       ║
║                                                                           ║
║  Three timer kinds                                                       ║
║                                                                           ║
║    one_shot — fires once at fires_at, then status=done                   ║
║    recurring — fires at fires_at, then re-arms with fires_at += interval ║
║    deadline — fires at fires_at (treated like one_shot, but semantically║
║               "this is a due-by, not a reminder")                       ║
║                                                                           ║
║  Dispatch                                                                ║
║                                                                           ║
║    When a timer fires, the registered handler is called with the        ║
║    Timer record. Handler decides what to do:                            ║
║      • emit a message into a chat                                       ║
║      • enqueue an agentic workflow task                                 ║
║      • run a project health check                                       ║
║      • etc.                                                              ║
║                                                                           ║
║  Safety                                                                  ║
║                                                                           ║
║    Timers may schedule but never silently execute impactful actions.    ║
║    The handler is responsible for routing through Aegis for anything    ║
║    R1+. Timers themselves are pure schedulers — they fire, they log,   ║
║    they hand off. They don't act unilaterally.                          ║
║                                                                           ║
║  Why we don't use APScheduler                                            ║
║                                                                           ║
║    Considered. Decided against for v0.2.37 because APScheduler adds a  ║
║    dependency and a second persistence mechanism. The skeleton needs   ║
║    to be small and inspectable. A 200-line poller against our own     ║
║    SQLite is honest. v0.2.38 can swap in APScheduler if scale demands ║
║    it; the timer API stays stable.                                     ║
║                                                                           ║
║  Kill switch: SOV_NO_TIMERS=1                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Optional

from ulid import ULID

from sovereign_agent.persistence.store import ErebloStore, _iso_now

logger = logging.getLogger(__name__)
KILL_SWITCH_ENV = "SOV_NO_TIMERS"


TimerKind = Literal["one_shot", "recurring", "deadline"]
TimerStatus = Literal["armed", "fired", "cancelled", "done"]


# ─── Record ──────────────────────────────────────────────────────────────


@dataclass
class Timer:
    timer_id: str
    name: str
    kind: TimerKind
    fires_at: str
    interval_sec: Optional[int]
    payload: dict[str, Any]
    status: TimerStatus
    chat_id: Optional[str]
    project_id: Optional[str]
    created_at: str
    updated_at: str
    last_fired_at: Optional[str]


def _row_to_timer(row) -> Timer:
    d = dict(row)
    payload = json.loads(d.pop("payload_json") or "{}")
    return Timer(payload=payload, **d)


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _fmt_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Clock manager ───────────────────────────────────────────────────────


TimerHandler = Callable[[Timer], None]


class ErebloClock:
    """The clock. Owns the timers table; runs a poller that fires due ones.

    Construct once. Call start() to begin the poller (background thread).
    Call stop() at shutdown.
    """

    def __init__(self, store: ErebloStore, poll_interval_sec: float = 1.0):
        self._store = store
        self._poll_interval = poll_interval_sec
        self._handlers: list[TimerHandler] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_ENV))

    # ─── Handler registration ───────────────────────────────────────────

    def register_handler(self, handler: TimerHandler) -> None:
        """Add a callable that gets invoked with each fired Timer.

        Multiple handlers permitted. They fire in registration order.
        Handler exceptions are caught and logged so one bad handler
        doesn't stop the others.
        """
        self._handlers.append(handler)

    # ─── Timer CRUD ─────────────────────────────────────────────────────

    def schedule_one_shot(
        self,
        name: str,
        fires_at: datetime,
        payload: Optional[dict[str, Any]] = None,
        chat_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        return self._schedule(
            "one_shot", name, fires_at, None, payload, chat_id, project_id,
        )

    def schedule_in(
        self,
        name: str,
        seconds_from_now: float,
        payload: Optional[dict[str, Any]] = None,
        chat_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        return self.schedule_one_shot(
            name=name,
            fires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now),
            payload=payload, chat_id=chat_id, project_id=project_id,
        )

    def schedule_recurring(
        self,
        name: str,
        interval_sec: int,
        first_fires_at: Optional[datetime] = None,
        payload: Optional[dict[str, Any]] = None,
        chat_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        if interval_sec < 1:
            raise ValueError("interval_sec must be >= 1")
        fires_at = first_fires_at or (
            datetime.now(timezone.utc) + timedelta(seconds=interval_sec)
        )
        return self._schedule(
            "recurring", name, fires_at, interval_sec, payload, chat_id, project_id,
        )

    def schedule_deadline(
        self,
        name: str,
        deadline_at: datetime,
        payload: Optional[dict[str, Any]] = None,
        chat_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        return self._schedule(
            "deadline", name, deadline_at, None, payload, chat_id, project_id,
        )

    def _schedule(
        self,
        kind: TimerKind,
        name: str,
        fires_at: datetime,
        interval_sec: Optional[int],
        payload: Optional[dict[str, Any]],
        chat_id: Optional[str],
        project_id: Optional[str],
    ) -> str:
        if self.is_disabled:
            raise RuntimeError("clock disabled via SOV_NO_TIMERS")
        timer_id = str(ULID())
        now = _iso_now()
        self._store.execute(
            "INSERT INTO timers(timer_id, name, kind, fires_at, interval_sec, "
            "payload_json, status, chat_id, project_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'armed', ?, ?, ?, ?)",
            (timer_id, name, kind, _fmt_iso(fires_at), interval_sec,
             json.dumps(payload or {}), chat_id, project_id, now, now),
        )
        return timer_id

    def cancel(self, timer_id: str) -> None:
        self._store.execute(
            "UPDATE timers SET status='cancelled', updated_at=? "
            "WHERE timer_id=? AND status='armed'",
            (_iso_now(), timer_id),
        )

    def get(self, timer_id: str) -> Optional[Timer]:
        row = self._store.query_one(
            "SELECT * FROM timers WHERE timer_id=?", (timer_id,)
        )
        return _row_to_timer(row) if row else None

    def list_armed(self, project_id: Optional[str] = None) -> list[Timer]:
        if project_id:
            rows = self._store.query_all(
                "SELECT * FROM timers WHERE status='armed' AND project_id=? "
                "ORDER BY fires_at ASC",
                (project_id,),
            )
        else:
            rows = self._store.query_all(
                "SELECT * FROM timers WHERE status='armed' "
                "ORDER BY fires_at ASC"
            )
        return [_row_to_timer(r) for r in rows]

    def upcoming(self, within_seconds: int = 3600) -> list[Timer]:
        """Armed timers due within the next N seconds."""
        cutoff = _fmt_iso(datetime.now(timezone.utc) + timedelta(seconds=within_seconds))
        rows = self._store.query_all(
            "SELECT * FROM timers WHERE status='armed' AND fires_at <= ? "
            "ORDER BY fires_at ASC",
            (cutoff,),
        )
        return [_row_to_timer(r) for r in rows]

    # ─── Poller ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.is_disabled:
            logger.info("clock disabled via SOV_NO_TIMERS; start() is a no-op")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="erebo-clock", daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_sec: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout_sec)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("clock tick failed")
            self._stop_event.wait(self._poll_interval)

    def _tick(self) -> None:
        """One poll cycle: find due timers, fire each, advance recurring ones."""
        now_iso = _iso_now()
        # Find armed timers whose fires_at <= now.
        rows = self._store.query_all(
            "SELECT * FROM timers WHERE status='armed' AND fires_at <= ? "
            "ORDER BY fires_at ASC",
            (now_iso,),
        )
        for row in rows:
            timer = _row_to_timer(row)
            # Advance state BEFORE handler runs — so a handler that takes
            # long doesn't cause re-fire.
            if timer.kind == "recurring":
                # Compute next fire time. Use interval-from-now to avoid drift
                # cascade if we missed many cycles.
                next_fires_at = _fmt_iso(
                    datetime.now(timezone.utc) + timedelta(seconds=timer.interval_sec or 60)
                )
                self._store.execute(
                    "UPDATE timers SET fires_at=?, last_fired_at=?, "
                    "updated_at=? WHERE timer_id=?",
                    (next_fires_at, now_iso, now_iso, timer.timer_id),
                )
            else:
                self._store.execute(
                    "UPDATE timers SET status='done', last_fired_at=?, "
                    "updated_at=? WHERE timer_id=?",
                    (now_iso, now_iso, timer.timer_id),
                )
            # Dispatch to handlers.
            for handler in self._handlers:
                try:
                    handler(timer)
                except Exception:
                    logger.exception(
                        "timer handler failed for timer_id=%s", timer.timer_id
                    )


__all__ = [
    "ErebloClock",
    "Timer", "TimerKind", "TimerStatus",
    "TimerHandler",
    "KILL_SWITCH_ENV",
]
