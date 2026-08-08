"""timers — every live countdown she's running, in one visible place.

Kevin's ask: see all her timers for the bots and her live task — how long
they've been alive and how long they're expected to live. Everything is
collected from PERSISTED state (heartbeat, source health, queue jobs,
ledgers, session files), so the collector needs no live runtime handle and
works identically inside the cockpit, the CLI, or a test.

Timer kinds:
  presence     — heartbeat age vs the 3-min awake window (when she'd read asleep)
  bot-poll     — per source: time since last fetch vs its allowed interval
                 (when the next poll is due)
  queue-retry  — a backed-off job counting down to its next attempt
  queue-lease  — an inflight job's crash-recovery lease
  uptime       — how long each bot has existed (ledger/audit birth → now)
  session      — an active work session's elapsed time
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = ["TimerRow", "gather_timers", "render_timers", "fmt_dur"]


@dataclass(frozen=True)
class TimerRow:
    kind: str
    name: str
    elapsed_s: float | None      # how long it has been alive/waiting
    expected_s: float | None     # its expected lifetime/interval (None = open-ended)
    remaining_s: float | None    # countdown to the next event (None = n/a)
    note: str = ""

    @property
    def fraction(self) -> float | None:
        """elapsed/expected for a progress bar; None when open-ended."""
        if self.expected_s and self.expected_s > 0 and self.elapsed_s is not None:
            return max(0.0, min(1.0, self.elapsed_s / self.expected_s))
        return None


def fmt_dur(s: float | None) -> str:
    if s is None:
        return "—"
    s = max(0.0, float(s))
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.0f}m"
    if s < 172800:
        return f"{s / 3600:.1f}h"
    return f"{s / 86400:.1f}d"


def _data_dir(data_dir: Path | None) -> Path | None:
    if data_dir is not None:
        return Path(data_dir)
    try:
        from sovereign_agent.config import SETTINGS
        return SETTINGS.paths.data_dir
    except Exception:  # noqa: BLE001
        return None


def _presence_rows(d: Path, now: float) -> list[TimerRow]:
    try:
        from sovereign_agent.presence import AWAKE_WINDOW_S, read_heartbeat
        hb = read_heartbeat(d)
        if not hb or "ts" not in hb:
            return [TimerRow("presence", "Aria (no heartbeat yet)", None,
                             AWAKE_WINDOW_S, None, "asleep")]
        age = max(0.0, now - float(hb["ts"]))
        awake = age <= AWAKE_WINDOW_S
        return [TimerRow("presence", "Aria heartbeat", age, AWAKE_WINDOW_S,
                         (AWAKE_WINDOW_S - age) if awake else None,
                         "🟢 awake" if awake else "🌙 asleep")]
    except Exception:  # noqa: BLE001
        return []


def _iso_to_epoch(iso: str) -> float | None:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _bot_rows(d: Path, now: float) -> list[TimerRow]:
    rows: list[TimerRow] = []
    try:
        from sovereign_agent.bot_projects import list_all
        from sovereign_agent.discord_runtime.bookkeeping import (
            read_ledger, read_source_health)
        from sovereign_agent.discord_runtime.queue import JobQueue
        from sovereign_agent.discord_runtime.runtime import _project_queue_dir
        from sovereign_agent.discord_runtime.sources import list_sources
        from sovereign_agent.shop_stats import read_runs

        for proj in list_all(d):
            pname = proj.project_name
            # uptime — birth from ledger, else the oldest audit line
            born = None
            led = read_ledger(d, pname)
            if led.get("created_at"):
                born = _iso_to_epoch(str(led["created_at"]))
            if born is None:
                runs = read_runs(d, pname)
                if runs:
                    born = min(float(r.get("ts", now)) for r in runs)
            if born is not None:
                rows.append(TimerRow("uptime", f"{pname}", now - born, None, None,
                                     "bot age (open-ended)"))
            # per-source next-poll countdowns — last fetch from telemetry
            health = read_source_health(d, pname)
            for src in list_sources(d, pname):
                h = health.get(src.name) or {}
                last = max(filter(None, (h.get("last_ok_ts"),
                                         h.get("last_error_ts"))), default=None)
                interval = float(src.allowed_min_interval_s)
                if last is None:
                    rows.append(TimerRow("bot-poll", f"{pname} · {src.name}",
                                         None, interval, 0.0,
                                         "never polled — due now"))
                else:
                    since = max(0.0, now - float(last))
                    rows.append(TimerRow(
                        "bot-poll", f"{pname} · {src.name}", since, interval,
                        max(0.0, interval - since),
                        "due" if since >= interval else "waiting"))
            # queue timers
            q = JobQueue(_project_queue_dir(d, pname))
            q._load()
            for job in q._pending:
                if job.status == "inflight":
                    rows.append(TimerRow(
                        "queue-lease", f"{pname} · {job.content[:28]}",
                        None, q.lease_ttl_s,
                        max(0.0, float(job.lease_until) - now),
                        f"inflight (attempt {job.attempts + 1})"))
                elif float(job.next_at) > now:
                    rows.append(TimerRow(
                        "queue-retry", f"{pname} · {job.content[:28]}",
                        None, None, float(job.next_at) - now,
                        f"retry #{job.attempts + 1} backing off"))
    except Exception:  # noqa: BLE001
        pass
    return rows


def _session_rows(d: Path, now: float) -> list[TimerRow]:
    rows: list[TimerRow] = []
    try:
        sessions = d / "sessions"
        if not sessions.is_dir():
            return rows
        for f in sorted(sessions.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if str(data.get("status", "")) != "active":
                continue
            born = _iso_to_epoch(str(data.get("created_at", ""))) or now
            goal = str(data.get("goal", ""))[:44]
            rows.append(TimerRow("session", f"work: {goal}", now - born, None,
                                 None, "live task (runs until done/budget)"))
    except Exception:  # noqa: BLE001
        pass
    return rows


def _attention_rows(d: Path, now: float) -> list[TimerRow]:
    """The observable attention queue: who she's serving, in policy order."""
    rows: list[TimerRow] = []
    try:
        from sovereign_agent.attention import AttentionQueue, ENTRY_TTL_S
        for i, e in enumerate(AttentionQueue(d).snapshot(now=now), 1):
            rows.append(TimerRow("attention", f"#{i} {e.label}",
                                 max(0.0, now - e.ts), ENTRY_TTL_S, None,
                                 f"{e.lane} lane"))
    except Exception:  # noqa: BLE001
        pass
    return rows


def gather_timers(data_dir: Path | None = None, *,
                  now: float | None = None) -> list[TimerRow]:
    now = time.time() if now is None else now
    d = _data_dir(data_dir)
    if d is None:
        return []
    return (_presence_rows(d, now) + _attention_rows(d, now)
            + _session_rows(d, now) + _bot_rows(d, now))


def _bar(fraction: float | None, width: int = 12) -> str:
    if fraction is None:
        return "·" * width
    filled = int(round(fraction * width))
    return "█" * filled + "░" * (width - filled)


def render_timers(rows: list[TimerRow]) -> str:
    if not rows:
        return "No timers yet — they appear as bots poll, jobs queue, and work runs."
    icons = {"presence": "💗", "session": "🛠", "uptime": "🌱",
             "bot-poll": "📡", "queue-retry": "⏳", "queue-lease": "🔒",
             "attention": "🎯"}
    lines: list[str] = []
    for r in rows:
        icon = icons.get(r.kind, "⏱")
        parts = [f"{icon} [b]{r.name}[/b]"]
        if r.elapsed_s is not None:
            parts.append(f"alive {fmt_dur(r.elapsed_s)}")
        if r.expected_s is not None:
            parts.append(f"of {fmt_dur(r.expected_s)}")
        if r.remaining_s is not None:
            parts.append(f"→ {fmt_dur(r.remaining_s)} left")
        lines.append("  ".join(parts))
        lines.append(f"    {_bar(r.fraction)}  [dim]{r.note}[/dim]")
    return "\n".join(lines)
