"""manager — supervise a fleet of bots with crash isolation.

The reliability capstone. A `BotManager` owns one durable `BotRuntime` per
defined project and drives them all on each `tick`:

  • **Crash isolation** — each bot's poll+drain is wrapped; one bot raising
    (a bad source, a parser bug) is caught, recorded, and the OTHER bots keep
    running. A single misbehaving bot can never take down the fleet.
  • **Durable by default** — every managed runtime gets the delivery queue
    (retry/backoff/dead-letter) and a delivery circuit breaker, so a
    transient Discord failure retries instead of dropping an alert, and a
    sustained failure trips the breaker instead of hammering.
  • **Honest status** — `status()` returns a per-bot snapshot (sources,
    pending, dead-letter, breaker state) for `sov bots fleet`/the cockpit.

Dry-run by default like everything else: a fleet built with `live=False`
monitors and queues but sends nothing outward.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sovereign_agent.bot_projects import BotProject, list_all

from .runtime import BotRuntime, build_runtime

__all__ = ["BotManager", "FleetTick", "BotStatus"]


@dataclass
class BotStatus:
    project: str
    sources: int
    polled: int = 0
    queued: int = 0
    sent: int = 0
    dry_run: int = 0
    pending: int = 0
    dead_letter: int = 0
    breaker: str = "closed"
    error: str = ""


@dataclass
class FleetTick:
    bots: list[BotStatus] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        alive = sum(1 for b in self.bots if not b.error)
        sent = sum(b.sent for b in self.bots)
        pending = sum(b.pending for b in self.bots)
        dead = sum(b.dead_letter for b in self.bots)
        line = f"fleet: {alive}/{len(self.bots)} healthy, {sent} sent, {pending} pending"
        if dead:
            line += f", {dead} dead-letter"
        if self.errors:
            line += f", {len(self.errors)} bot error(s)"
        return line


class BotManager:
    def __init__(self, data_dir: Path, *, live: bool = False,
                 on_live_send: Callable[[str], None] | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.live = live
        self._on_live_send = on_live_send
        self._runtimes: dict[str, BotRuntime] = {}

    def load(self) -> list[BotProject]:
        """(Re)build a durable runtime for every LIVE project. A project
        whose runtime can't be built (e.g. an impossible contract) is skipped
        with its error surfaced, never crashing the load.

        tracker-toggle-d (Kevin, 2026-07-25): "a way for me to turn
        channels on and maybe turn some channels off." `status` already
        had a "paused"/"retired" value — it just did nothing; every
        project loaded and polled regardless. Now a paused/retired
        project is genuinely skipped: no polling, no delivery, no
        Discord noise from it, until it's turned back on."""
        projects = [p for p in list_all(self.data_dir)
                   if p.status not in ("paused", "retired")]
        runtimes: dict[str, BotRuntime] = {}
        for p in projects:
            try:
                runtimes[p.project_name] = build_runtime(
                    p, self.data_dir, live=self.live, durable=True,
                    on_live_send=self._on_live_send)
            except Exception:  # noqa: BLE001 — one bad project can't stop the fleet
                continue
        self._runtimes = runtimes
        return projects

    def tick(self, now: float | None = None) -> FleetTick:
        now = time.time() if now is None else now
        if not self._runtimes:
            self.load()
        result = FleetTick()
        for name, rt in self._runtimes.items():
            status = BotStatus(project=name, sources=len(rt.sources))
            try:
                cycle = rt.poll_once(now)
                drain = rt.drain(now)
                status.polled = len(cycle.polled)
                status.queued = cycle.queued
                status.sent = drain.sent
                status.dry_run = drain.dry_run
                if rt.queue is not None:
                    status.pending = rt.queue.pending_count()
                    status.dead_letter = len(rt.queue.dead_letter())
                status.breaker = rt.breaker.state
            except Exception as exc:  # noqa: BLE001 — crash isolation
                status.error = f"{type(exc).__name__}: {exc}"
                result.errors.append(f"{name}: {status.error}")
            result.bots.append(status)
        return result

    def run(self, ticks: int = 1, now: float | None = None,
            step_s: float = 60.0) -> list[FleetTick]:
        now = time.time() if now is None else now
        out: list[FleetTick] = []
        for _ in range(max(1, ticks)):
            out.append(self.tick(now))
            now += step_s
        return out

    def status(self, now: float | None = None) -> list[BotStatus]:
        if not self._runtimes:
            self.load()
        now = time.time() if now is None else now
        rows: list[BotStatus] = []
        for name, rt in self._runtimes.items():
            row = BotStatus(project=name, sources=len(rt.sources),
                            breaker=rt.breaker.state)
            if rt.queue is not None:
                row.pending = rt.queue.pending_count()
                row.dead_letter = len(rt.queue.dead_letter())
            rows.append(row)
        return rows
