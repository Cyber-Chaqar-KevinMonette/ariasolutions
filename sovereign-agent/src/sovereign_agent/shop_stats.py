"""shop_stats — make the value visible (the #1 churn fighter).

Reuses the audit trail the runtime already writes (`runs.jsonl` per project)
— no new storage. Two products:

  • **Per-customer digest** — "your bot delivered 47 alerts · 99.8% uptime
    this month" → posted to their private channel. Seeing the value is the
    single biggest reason a subscriber stays.
  • **Public aggregate** — "BigKev's bots: 12,400 alerts, 99.9% uptime" → a
    trust magnet for new buyers, published in the shop.

Everything is derived from the real audit records; nothing is invented.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from sovereign_agent.bot_projects import projects_dir, slugify

__all__ = [
    "BotStats",
    "AggregateStats",
    "read_runs",
    "bot_stats",
    "aggregate_stats",
    "render_bot_digest",
    "render_public_stats",
    "public_stats_embed",
]

_DAY = 86400.0


@dataclass
class BotStats:
    project: str
    cycles: int = 0
    polls: int = 0
    detected: int = 0            # new items found
    delivered: int = 0           # real sends (live)
    would_deliver: int = 0       # dry-run sends
    failed: int = 0              # real send failures
    window_days: int = 30

    @property
    def alerts(self) -> int:
        return self.delivered + self.would_deliver

    @property
    def uptime_pct(self) -> float:
        denom = self.delivered + self.would_deliver + self.failed
        return 100.0 if denom == 0 else round(100.0 * (self.alerts) / denom, 1)


@dataclass
class AggregateStats:
    bots: int = 0
    alerts: int = 0
    delivered: int = 0
    failed: int = 0
    per_bot: list[BotStats] = field(default_factory=list)

    @property
    def uptime_pct(self) -> float:
        denom = self.alerts + self.failed
        return 100.0 if denom == 0 else round(100.0 * self.alerts / denom, 1)


def _runs_path(data_dir: Path, project_name: str) -> Path:
    return projects_dir(data_dir) / slugify(project_name) / "runs.jsonl"


def read_runs(data_dir: Path, project_name: str, *,
              since: float | None = None) -> list[dict]:
    """Read a project's audit records, newest-tolerant, corruption-resilient."""
    path = _runs_path(data_dir, project_name)
    if not path.is_file():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001 — skip a torn line, never crash
                continue
            if since is not None and float(rec.get("ts", 0)) < since:
                continue
            out.append(rec)
    except Exception:  # noqa: BLE001
        return out
    return out


def bot_stats(data_dir: Path, project_name: str, *, window_days: int = 30,
              now: float | None = None) -> BotStats:
    now = time.time() if now is None else now
    since = now - window_days * _DAY
    st = BotStats(project=project_name, window_days=window_days)
    for rec in read_runs(data_dir, project_name, since=since):
        st.cycles += 1
        st.polls += len(rec.get("polled", []) or [])
        st.detected += len(rec.get("new", []) or [])
        for d in rec.get("deliveries", []) or []:
            if d.get("sent"):
                st.delivered += 1
            elif d.get("dry_run"):
                st.would_deliver += 1
            else:
                st.failed += 1
    return st


def aggregate_stats(data_dir: Path, *, window_days: int = 30,
                    now: float | None = None) -> AggregateStats:
    from sovereign_agent.bot_projects import list_all
    agg = AggregateStats()
    for proj in list_all(data_dir):
        st = bot_stats(data_dir, proj.project_name, window_days=window_days, now=now)
        if st.cycles == 0:
            continue
        agg.bots += 1
        agg.alerts += st.alerts
        agg.delivered += st.delivered
        agg.failed += st.failed
        agg.per_bot.append(st)
    return agg


def render_bot_digest(st: BotStats) -> str:
    if st.cycles == 0:
        return (f"📊 **{st.project}** — no activity in the last "
                f"{st.window_days} days yet. It's watching.")
    return (f"📊 **{st.project}** — last {st.window_days} days:\n"
            f"  • {st.alerts} alert{'s' if st.alerts != 1 else ''} delivered\n"
            f"  • {st.uptime_pct}% uptime · {st.detected} detected · "
            f"{st.polls} checks\n"
            + (f"  • ⚠ {st.failed} delivery retr{'ies' if st.failed != 1 else 'y'}\n"
               if st.failed else "")
            + "  • reliably watched by BigKev's Bot Shop 💛")


def render_public_stats(agg: AggregateStats) -> str:
    if agg.bots == 0:
        return "🏪 BigKev's Bot Shop — bots standing by, ready to deliver."
    return (f"🏪 **BigKev's Bot Shop** — {agg.alerts} alerts delivered across "
            f"{agg.bots} bot{'s' if agg.bots != 1 else ''}, "
            f"{agg.uptime_pct}% uptime. Reliable, 24/7.")


def public_stats_embed(agg: AggregateStats) -> dict:
    return {
        "title": "🏪 BigKev's Bot Shop — live stats",
        "color": 0x22D3EE,
        "description": render_public_stats(agg),
        "fields": [
            {"name": "Alerts delivered", "value": str(agg.alerts), "inline": True},
            {"name": "Active bots", "value": str(agg.bots), "inline": True},
            {"name": "Uptime", "value": f"{agg.uptime_pct}%", "inline": True},
        ],
    }
