"""discord_watch — everything she does and learns on Discord, one stream.

Kevin's ask: watch her work Discord all day/night from the cockpit —
"everything she does and learns." She already writes honest ledgers for
every lane; this module is the unifying READ layer (no new storage):

  • ask_aria/log.ndjson        → customers answered / probes deflected
  • discord_admin/audit.jsonl  → server ops (setup, webhooks, welcomes, scans)
  • bot_projects/*/runs.jsonl  → alert deliveries per bot
  • welcome/welcomed.json      → members greeted
  • advertising/state.json     → ads posted
  • success_patterns.ndjson    → what she LEARNED works
  • bot_projects/*/source_health.json → sources going bad (flagged live)
  • attention/queue.json       → who she's serving right now
  • discord_duty/ledger.ndjson → the duty loop's own tick summaries

Contract: pure reads, time-sorted merge, a missing or corrupt ledger just
means that lane contributes nothing — NEVER an exception. The cockpit's
⌁ Discord Watch screen and the "what's happening on discord?" bridge both
render from here.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ActivityRow",
    "gather_activity",
    "duty_status",
    "render_activity",
    "compose_discord_report",
    "is_discord_watch_query",
]


@dataclass(frozen=True)
class ActivityRow:
    ts: float
    icon: str
    lane: str        # customer|server|bots|welcome|ads|learning|health|duty
    text: str


def _ndjson(path: Path, limit: int = 400) -> list[dict]:
    """Last `limit` records of an NDJSON file; torn lines skipped."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                out.append(rec)
        except Exception:  # noqa: BLE001
            continue
    return out


# ── per-lane readers (each: rows or [], never raises) ────────────────────────
def _ask_rows(d: Path) -> list[ActivityRow]:
    icons = {"deflected": ("🛡", "deflected an extraction probe from"),
             "silent": ("▫", "stayed silent (anti-spam) to"),
             "llm": ("»", "chatted (live voice) with"),
             "limited": ("⚐", "asked patience of"),
             "resting": ("☾", "answered while resting:")}
    rows = []
    for r in _ndjson(d / "ask_aria" / "log.ndjson"):
        kind = str(r.get("kind", ""))
        icon, verb = icons.get(kind, ("‣", f"answered ({kind or 'shop'})"))
        q = str(r.get("q", ""))[:60]
        rows.append(ActivityRow(float(r.get("ts", 0)), icon, "customer",
                                f"{verb} {str(r.get('user', '?'))[:16]} — '{q}'"))
    return rows


def _admin_rows(d: Path) -> list[ActivityRow]:
    labels = {
        "setup_shop": ("🏗", "built/repaired the server"),
        "setup_webhook": ("⚒", "provisioned a webhook"),
        "welcome": ("☘", "welcomed a new member"),
        "scan_server": ("⊚", "scanned the server vs the plan"),
        "auto_scan": ("⊚", "auto-scanned on connect"),
        "create_channel": ("+", "created a channel"),
        "create_role": ("+", "created a role"),
        "ready": ("↯", "came online (gateway connected)"),
        "ma": ("✉", "mail for Aria (/ma)"),
    }
    rows = []
    for r in _ndjson(d / "discord_admin" / "audit.jsonl"):
        op = str(r.get("op", ""))
        icon, label = labels.get(op, ("⚙", op or "op"))
        extra = ""
        if op == "setup_webhook":
            extra = f" on #{r.get('channel', '?')} → {r.get('env', '')}"
        elif op == "auto_scan":
            extra = (f" — coverage {float(r.get('coverage', 0)):.0%}, "
                     f"{int(r.get('missing', 0))} missing")
        elif op in ("create_channel", "create_role"):
            extra = f": {r.get('name', '')}"
        elif op == "ma":
            who = "Kevin (owner)" if r.get("owner") else f"member {r.get('user', '?')}"
            extra = f" from {who}"
        if r.get("error"):
            icon, extra = "✗", f" FAILED ({r.get('error')})"
        rows.append(ActivityRow(float(r.get("ts", 0)), icon, "server",
                                f"{label}{extra}"))
    return rows


def _bot_rows(d: Path) -> list[ActivityRow]:
    rows = []
    projects = d / "bot_projects"
    try:
        proj_dirs = [p for p in projects.iterdir() if p.is_dir()]
    except Exception:  # noqa: BLE001
        return []
    for proj in proj_dirs[:50]:
        for r in _ndjson(proj / "runs.jsonl", limit=100):
            if r.get("rollup"):
                continue
            new = r.get("new") or []
            deliveries = r.get("deliveries") or []
            sent = sum(1 for x in deliveries if x.get("sent"))
            if not new and not sent:
                continue          # quiet poll — not activity
            note = f"found {len(new)} new item(s)"
            if sent:
                note += f", delivered {sent} alert(s)"
            elif deliveries:
                note += f", {len(deliveries)} dry-run"
            rows.append(ActivityRow(float(r.get("ts", 0)), "➤", "bots",
                                    f"{proj.name}: {note}"))
            # mirror-d (Kevin, 2026-07-18): "everything she posts in the
            # discord also shows in the cockpit" — each LIVE-delivered
            # find mirrors as its own row (the audit already carries the
            # clean title; bounded to 3 per run so a burst can't flood).
            if sent:
                for item in new[:3]:
                    txt = str(item.get("text", "")).strip()
                    if txt:
                        rows.append(ActivityRow(
                            float(r.get("ts", 0)), "➤", "bots",
                            f"{proj.name} posted: {txt[:110]}"))
    return rows


def _welcome_rows(d: Path) -> list[ActivityRow]:
    try:
        raw = json.loads((d / "welcome" / "welcomed.json").read_text(
            encoding="utf-8"))
        return [ActivityRow(float(ts), "☘", "welcome",
                            f"greeted member {str(mid)[:16]} (first time ever)")
                for mid, ts in raw.items()] if isinstance(raw, dict) else []
    except Exception:  # noqa: BLE001
        return []


def _ad_rows(d: Path) -> list[ActivityRow]:
    try:
        raw = json.loads((d / "advertising" / "state.json").read_text(
            encoding="utf-8"))
        last = raw.get("last_sent_ts")
        if last is None:
            return []
        return [ActivityRow(float(last), "✷", "ads",
                            f"posted ad (rotation slot {int(raw.get('index', 0))})")]
    except Exception:  # noqa: BLE001
        return []


def _learning_rows(d: Path) -> list[ActivityRow]:
    rows = []
    for r in _ndjson(d / "success_patterns.ndjson", limit=100):
        outcome = str(r.get("outcome", ""))
        icon = "✶" if outcome == "done" else "✳"
        verdict = "worked" if outcome == "done" else f"ended: {outcome}"
        rows.append(ActivityRow(float(r.get("ts", 0)), icon, "learning",
                                f"learned: '{str(r.get('goal', ''))[:70]}' "
                                f"{verdict} ({int(r.get('subtasks_done', 0))}/"
                                f"{int(r.get('subtasks_total', 0))} steps)"))
    return rows


def _health_rows(d: Path, now: float) -> list[ActivityRow]:
    rows = []
    projects = d / "bot_projects"
    try:
        proj_dirs = [p for p in projects.iterdir() if p.is_dir()]
    except Exception:  # noqa: BLE001
        return []
    for proj in proj_dirs[:50]:
        try:
            raw = json.loads((proj / "source_health.json").read_text(
                encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for source, h in (raw.items() if isinstance(raw, dict) else []):
            fails = int(h.get("consecutive_failures", 0) or 0)
            if fails >= 3:
                rows.append(ActivityRow(
                    float(h.get("last_error_ts") or now), "▪", "health",
                    f"{proj.name}: source '{source}' failing ×{fails} "
                    f"({str(h.get('last_error', ''))[:40]})"))
    return rows


def _duty_rows(d: Path) -> list[ActivityRow]:
    return [ActivityRow(float(r.get("ts", 0)), "✦", "duty",
                        str(r.get("summary", "duty tick"))[:120])
            for r in _ndjson(d / "discord_duty" / "ledger.ndjson", limit=50)
            if r.get("notable")]      # quiet ticks stay out of the feed


def record_duty_tick(data_dir: Path, summary: str, *, notable: bool = False,
                     now: float | None = None) -> None:
    """One duty-loop ledger line. `notable=False` ticks are heartbeat
    bookkeeping (kept for the status header, hidden from the feed)."""
    try:
        now = time.time() if now is None else now
        d = Path(data_dir) / "discord_duty"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "ledger.ndjson", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": now, "summary": str(summary)[:200],
                                 "notable": bool(notable)},
                                ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def gather_activity(data_dir: Path | None = None, *, limit: int = 100,
                    now: float | None = None) -> list[ActivityRow]:
    """The merged, newest-first stream of everything she did on Discord."""
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return []
    d = Path(data_dir)
    now = time.time() if now is None else now
    rows: list[ActivityRow] = []
    for reader in (_ask_rows, _admin_rows, _bot_rows, _welcome_rows,
                   _ad_rows, _learning_rows, _duty_rows):
        try:
            rows.extend(reader(d))
        except Exception:  # noqa: BLE001 — one lane must never sink the feed
            continue
    try:
        rows.extend(_health_rows(d, now))
    except Exception:  # noqa: BLE001
        pass
    rows.sort(key=lambda r: r.ts, reverse=True)
    return rows[:limit]


# ── status header ────────────────────────────────────────────────────────────
def duty_status(data_dir: Path | None = None, *,
                now: float | None = None) -> dict:
    """The at-a-glance header: is the duty loop alive, is the bot on the
    gateway, presence, queue depth, today's counts."""
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            data_dir = Path(".")
    d = Path(data_dir)
    now = time.time() if now is None else now

    def _last_ts(rows: list[dict]) -> float | None:
        return float(rows[-1]["ts"]) if rows else None

    duty_ts = _last_ts(_ndjson(d / "discord_duty" / "ledger.ndjson", limit=5))
    bot_ts = _last_ts(_ndjson(d / "discord_admin" / "audit.jsonl", limit=5))
    awake = False
    try:
        from sovereign_agent.presence import presence_status
        awake = presence_status(d, now=now).awake
    except Exception:  # noqa: BLE001
        pass
    queue_depth = 0
    try:
        from sovereign_agent.attention import AttentionQueue
        queue_depth = len(AttentionQueue(d).snapshot(now=now))
    except Exception:  # noqa: BLE001
        pass
    day_start = now - (now % 86400)
    today = [r for r in gather_activity(d, limit=400, now=now)
             if r.ts >= day_start]
    counts = {"answered": sum(1 for r in today if r.lane == "customer"),
              "delivered": sum(1 for r in today if r.lane == "bots"),
              "welcomed": sum(1 for r in today if r.lane == "welcome"),
              "ads": sum(1 for r in today if r.lane == "ads"),
              "learned": sum(1 for r in today if r.lane == "learning")}
    services = ""
    try:      # services-d: RUNNING/STOPPED straight from systemd (the truth)
        from sovereign_agent.bot_services import states_line
        services = states_line()
    except Exception:  # noqa: BLE001
        pass
    return {"duty_age_s": (now - duty_ts) if duty_ts else None,
            "bot_age_s": (now - bot_ts) if bot_ts else None,
            "awake": awake, "queue_depth": queue_depth, "today": counts,
            "services": services}


def _age_word(age_s: float | None, fresh_s: float) -> str:
    if age_s is None:
        return "not seen"
    if age_s <= fresh_s:
        return "live"
    if age_s < 3600:
        return f"quiet {age_s / 60:.0f}m"
    return f"quiet {age_s / 3600:.1f}h"


def render_activity(data_dir: Path | None = None, *, limit: int = 30,
                    now: float | None = None) -> str:
    now = time.time() if now is None else now
    s = duty_status(data_dir, now=now)
    t = s["today"]
    lines = [
        "⌁ Discord Watch — her shift, live",
        f"  duty loop: {_age_word(s['duty_age_s'], 180)} · admin bot: "
        f"{_age_word(s['bot_age_s'], 900)} · presence: "
        f"{'◉ awake' if s['awake'] else '☾ asleep'} · queue: {s['queue_depth']}"
        + (f" · services: {s['services']}" if s.get("services") else ""),
        f"  today: {t['answered']} answered · {t['delivered']} bot deliveries"
        f" · {t['welcomed']} welcomed · {t['ads']} ads · {t['learned']} learned",
        "",
    ]
    rows = gather_activity(data_dir, limit=limit, now=now)
    if not rows:
        lines.append("  (no Discord activity recorded yet — she's ready)")
    for r in rows:
        hhmm = time.strftime("%m-%d %H:%M", time.localtime(r.ts))
        lines.append(f"  {hhmm}  {r.icon} {r.text}")
    return "\n".join(lines)


# ── the chat bridge (PRECISE triggers — lesson 16) ───────────────────────────
# PRECISE on purpose (lesson 16): "what did you do on discord" belongs to
# the work bridge and "how's the shop doing" to the shop bridge (dispatch
# order) — the collision matrix caught both. These are discord-watch's own.
_WATCH_TRIGGERS: tuple[str, ...] = (
    "what's happening on discord", "whats happening on discord",
    "what is happening on discord", "discord activity",
    "discord watch", "discord report", "how's the shift",
    "hows the shift", "how is the shift", "shop activity",
)


def is_discord_watch_query(text: str) -> bool:
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _WATCH_TRIGGERS)


def compose_discord_report(data_dir: Path | None = None) -> str:
    return render_activity(data_dir, limit=15)
