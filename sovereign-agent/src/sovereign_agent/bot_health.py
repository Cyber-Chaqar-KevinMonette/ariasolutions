"""bot_health — so Aria always knows if her bots need attention or updates.

Kevin's ask: she should always know whether the bots are healthy or need a
look, WITHOUT it eating her attention (bots stay first, automated). This is a
cross-process scan built from *persisted* signals only (no live manager
needed), so `sov bots health` / the chat bridge / the daemon can all read the
same truth:

  • sources configured? (no sources → she can't deliver anything)
  • durable queue: pending backlog + dead-letter count (delivery failing?)
  • last delivery age (has it gone quiet — dead feed, or daemon not running?)

Each bot gets an **attention level** — ok · watch · needs-attention — with
plain-language reasons Aria can relay ("Restock bot: 3 alerts dead-lettered —
check the webhook"). Reuses the queue, source store, and runs.jsonl audit we
already have; adds no new storage.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from sovereign_agent.bot_projects import BotProject, list_all

__all__ = [
    "BotAttention",
    "OK",
    "WATCH",
    "NEEDS_ATTENTION",
    "scan_bots",
    "compose_bot_attention_report",
    "is_bot_health_query",
]

OK = "ok"
WATCH = "watch"
NEEDS_ATTENTION = "needs-attention"

_LEVEL_RANK = {OK: 0, WATCH: 1, NEEDS_ATTENTION: 2}
_LEVEL_ICON = {OK: "🟢", WATCH: "🟡", NEEDS_ATTENTION: "🔴"}

# thresholds (tunable)
PENDING_BACKLOG = 25          # queued-but-undelivered above this = watch
QUIET_HOURS = 48.0            # no delivery in this long (with sources) = watch


@dataclass
class BotAttention:
    project: str
    level: str = OK
    reasons: list[str] = field(default_factory=list)
    sources: int = 0
    pending: int = 0
    dead_letter: int = 0
    last_delivery_age_h: float | None = None
    # webhook-blindspot-d: True/False/None(unknown) — see _has_webhook()
    has_webhook: bool | None = None

    @property
    def icon(self) -> str:
        return _LEVEL_ICON.get(self.level, "⚪")

    def _raise(self, level: str, reason: str) -> None:
        self.reasons.append(reason)
        if _LEVEL_RANK[level] > _LEVEL_RANK[self.level]:
            self.level = level


def _queue_counts(data_dir: Path, project_name: str) -> tuple[int, int]:
    try:
        from sovereign_agent.discord_runtime.queue import JobQueue
        from sovereign_agent.discord_runtime.runtime import _project_queue_dir
        q = JobQueue(_project_queue_dir(data_dir, project_name))
        return (q.pending_count(), len(q.dead_letter()))
    except Exception:  # noqa: BLE001
        return (0, 0)


def _last_delivery_age_h(data_dir: Path, project_name: str, now: float) -> float | None:
    try:
        from sovereign_agent.shop_stats import read_runs
        runs = read_runs(data_dir, project_name)
        if not runs:
            return None
        last_ts = max(float(r.get("ts", 0)) for r in runs)
        return max(0.0, (now - last_ts) / 3600.0)
    except Exception:  # noqa: BLE001
        return None


def _source_count(data_dir: Path, project_name: str) -> int:
    try:
        from sovereign_agent.discord_runtime.sources import list_sources
        return len(list_sources(data_dir, project_name))
    except Exception:  # noqa: BLE001
        return 0


def _has_webhook(project: BotProject) -> bool | None:
    """Is there a real delivery target for this bot?

    webhook-blindspot-d (Kevin, 2026-08-03): "if it does not report to the
    discord it fails." Measured live that day: 23 of 84 verticals had NO
    webhook configured at all — they could never post — and every one of
    them reported "healthy — delivering normally", because this file only
    ever looked at sources/queue/age and never asked whether there was
    anywhere to send. #condos and #apartments had been empty since the day
    they were created while the dashboard showed green.

    Returns None (unknown → don't judge) if the project declares no
    webhook_env at all, so hand-made projects that deliver another way
    aren't slandered as broken.
    """
    env_name = (getattr(project, "webhook_env", "") or "").strip()
    if not env_name:
        return None
    import os
    if (os.environ.get(env_name) or "").strip():
        return True
    try:                                    # fall back to the vault
        from sovereign_agent.credentials import read_env
        return bool((read_env().get(env_name) or "").strip())
    except Exception:  # noqa: BLE001
        return None                         # can't tell — stay quiet


def assess_bot(data_dir: Path, project: BotProject, *, now: float | None = None) -> BotAttention:
    now = time.time() if now is None else now
    a = BotAttention(project=project.project_name)
    a.sources = _source_count(data_dir, project.project_name)
    a.has_webhook = _has_webhook(project)
    a.pending, a.dead_letter = _queue_counts(data_dir, project.project_name)
    a.last_delivery_age_h = _last_delivery_age_h(data_dir, project.project_name, now)

    # R5a — link-rot telemetry: consecutive fetch failures make a dead link
    # DISTINGUISHABLE from a quiet feed, with evidence she can relay.
    #
    # source-health-disabled-d (Kevin, 2026-08-02): "fix the bots" surfaced
    # a real bug -- source_health.json keeps a source's failure history
    # forever, even after it's disabled via set_source_enabled/
    # set_reddit_sources_enabled. A disabled source will never be polled
    # again (BotRuntime.poll_once() skips it), so its stale failure count
    # should never raise NEEDS_ATTENTION -- that's not a live problem,
    # it's history from before the operator turned it off on purpose.
    try:
        from sovereign_agent.discord_runtime.sources import list_sources
        enabled_names = {s.name for s in list_sources(data_dir, project.project_name)
                         if s.enabled}
    except Exception:  # noqa: BLE001
        enabled_names = None  # unknown -- don't filter, fail open to the old behavior
    try:
        from sovereign_agent.discord_runtime.bookkeeping import (
            FAILING_THRESHOLD, read_source_health)
        for sname, h in (read_source_health(data_dir, project.project_name) or {}).items():
            if enabled_names is not None and sname not in enabled_names:
                continue  # disabled (or removed) -- stale history, not a live issue
            fails = int(h.get("consecutive_failures", 0))
            if fails >= FAILING_THRESHOLD:
                err = h.get("last_error", "") or "failing"
                a._raise(NEEDS_ATTENTION,
                         f"source '{sname}' failing ({err}) ×{fails} in a row — "
                         f"the link looks dead or needs updating")
    except Exception:  # noqa: BLE001
        pass

    # webhook-blindspot-d: no delivery target = it CANNOT report to Discord,
    # no matter how healthy everything upstream looks. Kevin's bar: "if it
    # does not report to the discord it fails." Checked FIRST because it
    # makes every other signal moot.
    if a.has_webhook is False:
        a._raise(NEEDS_ATTENTION,
                 f"no webhook configured (${getattr(project, 'webhook_env', '?')}) "
                 f"— it can never post to Discord, whatever else looks fine")
    if a.sources == 0:
        a._raise(NEEDS_ATTENTION, "no sources configured — nothing to monitor yet")
    if a.dead_letter > 0:
        a._raise(NEEDS_ATTENTION,
                 f"{a.dead_letter} alert(s) dead-lettered — delivery is failing "
                 f"(check the webhook/target)")
    if a.pending > PENDING_BACKLOG:
        a._raise(WATCH, f"{a.pending} alerts queued and undelivered — is the daemon running?")
    if a.sources > 0 and a.last_delivery_age_h is None:
        a._raise(WATCH, "no delivery activity recorded yet")
    elif a.last_delivery_age_h is not None and a.last_delivery_age_h > QUIET_HOURS:
        a._raise(WATCH, f"quiet for {a.last_delivery_age_h:.0f}h — dead feed, or "
                        f"the daemon isn't running?")
    if not a.reasons:
        a.reasons.append("healthy — delivering normally")
    return a


def scan_bots(data_dir: Path, *, now: float | None = None) -> list[BotAttention]:
    """Attention report for every defined bot, worst first."""
    out = [assess_bot(data_dir, p, now=now) for p in list_all(data_dir)]
    out.sort(key=lambda a: (-_LEVEL_RANK[a.level], a.project.lower()))
    return out


def compose_bot_attention_report(data_dir: Path | None = None, *,
                                 now: float | None = None) -> str:
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return "I can't read the bot data right now."
    bots = scan_bots(data_dir, now=now)
    if not bots:
        return ("No bots defined yet — nothing to watch. Open the Bot Studio "
                "(/bots) when you're ready to build one.")
    need = [b for b in bots if b.level == NEEDS_ATTENTION]
    watch = [b for b in bots if b.level == WATCH]
    healthy = [b for b in bots if b.level == OK]
    head = (f"🤖 {len(bots)} bot(s): {len(healthy)} healthy, "
            f"{len(watch)} to watch, {len(need)} need attention.")
    lines = [head]
    for b in bots:
        if b.level == OK:
            continue
        lines.append(f"  {b.icon} [b]{b.project}[/b] — {b.reasons[0]}")
    if not need and not watch:
        lines.append("  🟢 All bots healthy and delivering. Nothing needs you. 💛")
    else:
        lines.append("  [dim]The rest are healthy. Bots keep running on their own — "
                     "this is just so you know.[/dim]")
    return "\n".join(lines)


_HEALTH_TRIGGERS = (
    "how are the bots", "bot health", "do any bots need", "bots need attention",
    "which bots need", "bots need updates", "check the bots", "bot status",
    "are the bots ok", "how are our bots", "do the bots need",
)


def is_bot_health_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _HEALTH_TRIGGERS)
