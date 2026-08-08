"""moderation.py — 🛡 graduated, audited moderation (guards + auto-mute).

Kevin's ask: "high guards against members who poke inappropriately — she can
mute them until staff review, and report it to me."

Safety shape (her kernel: power proportional to reversibility):
  • **warn / mute** (Discord timeout — REVERSIBLE): Aria may do these herself
    when thresholds are met (e.g. repeated prompt-extraction probing), always
    with a reason + a discretion estimate, always ledgered, always reported.
  • **kick / ban** (hard to reverse): Aria may only **propose** — a human
    approves. (Proposals live in the same ledger, status "proposed".)

Bounded autonomy: an auto-mute is short (default 15 min) and capped to **one
per user per day** — so a bad actor is paused for staff review, never
silenced indefinitely by a machine. Every action is an append-only ledger
line (audited, visible in Discord Watch) and reported to the owner.

Pure + tested: this owns the ledger, the discretion scorer, and the
auto-mute *policy*; applying the Discord timeout + reporting live in
`discord_admin/bot.py`.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

WARN = "warn"
MUTE = "mute"
UNMUTE = "unmute"
KICK_PROPOSED = "kick_proposed"
BAN_PROPOSED = "ban_proposed"
NOTE = "note"

# an auto-mute is short + rare by design
AUTO_MUTE_SECONDS = 15 * 60
AUTO_MUTE_DAILY_CAP = 1


def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "moderation"


def _ledger(data_dir: Path) -> Path:
    return _dir(data_dir) / "ledger.ndjson"


def discretion(severity: int, confidence: float, rationale: str) -> dict:
    """How clear-cut was this? severity 1-5, confidence 0-1, + a one-liner
    on why THIS action and not a softer one."""
    return {"severity": max(1, min(int(severity), 5)),
            "confidence": max(0.0, min(float(confidence), 1.0)),
            "rationale": str(rationale or "")[:300]}


def record(data_dir: Path, action: str, target_id: str, target_name: str,
           reason: str, *, evidence: str = "", severity: int = 2,
           confidence: float = 0.5, rationale: str = "",
           decided_by: str = "aria-auto", duration_s: int = 0,
           now: float | None = None) -> dict:
    """Append one moderation record. `reason` is always required in spirit —
    an empty reason is stored as '(unspecified)' so nothing is unaccountable."""
    now = time.time() if now is None else now
    rec = {"ts": now, "action": action, "target_id": str(target_id),
           "target_name": str(target_name or target_id),
           "reason": str(reason or "(unspecified)")[:400],
           "evidence": str(evidence or "")[:600],
           "discretion": discretion(severity, confidence, rationale),
           "decided_by": decided_by, "duration_s": int(duration_s)}
    p = _ledger(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return rec


def _read(data_dir: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for line in _ledger(data_dir).read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return []
    return out


def history(data_dir: Path, target_id: str | None = None,
            limit: int = 50) -> list[dict]:
    rows = _read(data_dir)
    if target_id is not None:
        rows = [r for r in rows if r.get("target_id") == str(target_id)]
    return rows[-limit:][::-1]


def auto_mutes_since(data_dir: Path, target_id: str, within_s: float,
                     *, now: float | None = None) -> int:
    now = time.time() if now is None else now
    cutoff = now - within_s
    return sum(1 for r in _read(data_dir)
               if r.get("target_id") == str(target_id)
               and r.get("action") == MUTE
               and r.get("decided_by") == "aria-auto"
               and r.get("ts", 0) >= cutoff)


def may_auto_mute(data_dir: Path, target_id: str, *,
                  now: float | None = None) -> bool:
    """Bounded: at most AUTO_MUTE_DAILY_CAP auto-mutes per user per 24h.
    Beyond that she stops muting and only reports — a human takes over."""
    return auto_mutes_since(data_dir, target_id, 86400.0, now=now) \
        < AUTO_MUTE_DAILY_CAP


def auto_mute_decision(strikes: int) -> dict:
    """Turn a strike count into a mute decision + discretion. More strikes →
    higher severity, but the duration stays short + reviewable."""
    severity = min(5, 2 + max(0, strikes - 3))       # 3 strikes → sev 2
    confidence = min(1.0, 0.6 + 0.1 * max(0, strikes - 3))
    return {"duration_s": AUTO_MUTE_SECONDS, "severity": severity,
            "confidence": confidence,
            "rationale": (f"{strikes} extraction/probe strikes in the window "
                          "— short mute for staff to review, not a ban.")}


def active_mutes(data_dir: Path, *, now: float | None = None) -> list[dict]:
    """Mutes whose window hasn't elapsed and weren't later unmuted."""
    now = time.time() if now is None else now
    unmuted = {r["target_id"] for r in _read(data_dir)
               if r.get("action") == UNMUTE}
    out = []
    for r in _read(data_dir):
        if r.get("action") != MUTE:
            continue
        ends = r.get("ts", 0) + r.get("duration_s", 0)
        if ends > now and r.get("target_id") not in unmuted:
            out.append(r)
    return out


def compose_mod_report(data_dir: Path, *, limit: int = 12) -> str:
    """The owner's moderation view — recent actions + who's muted now."""
    rows = history(data_dir, limit=limit)
    if not rows:
        return "🛡 **Moderation** — all quiet. No actions on record. 💛"
    badge = {WARN: "⚠ warn", MUTE: "🔇 mute", UNMUTE: "🔊 unmute",
             KICK_PROPOSED: "👢 kick?", BAN_PROPOSED: "🔨 ban?", NOTE: "📝"}
    lines = [f"🛡 **Moderation** — last {len(rows)} actions:", ""]
    for r in rows:
        d = r.get("discretion", {})
        dur = f" · {r['duration_s']//60}m" if r.get("duration_s") else ""
        lines.append(
            f"{badge.get(r['action'], r['action'])} · **{r['target_name']}**"
            f"{dur} · {r['reason'][:60]} "
            f"_(sev {d.get('severity','?')}, {r.get('decided_by','?')})_")
    active = active_mutes(data_dir)
    if active:
        lines += ["", f"🔇 currently muted: "
                  + ", ".join(m["target_name"] for m in active)]
    return "\n".join(lines)


def compose_owner_alert(rec: dict) -> str:
    """The heads-up Aria sends Kevin the moment she auto-mutes someone."""
    d = rec.get("discretion", {})
    mins = rec.get("duration_s", 0) // 60
    return (f"🛡 I muted **{rec['target_name']}** for {mins}m — {rec['reason']}\n"
            f"Evidence: {rec.get('evidence', '')[:200]}\n"
            f"(severity {d.get('severity','?')}, confidence "
            f"{d.get('confidence','?')}) · reversible — `/mod unmute "
            f"{rec['target_id']}` if it was a misread. Held for your review.")


__all__ = [
    "WARN", "MUTE", "UNMUTE", "KICK_PROPOSED", "BAN_PROPOSED", "NOTE",
    "AUTO_MUTE_SECONDS", "AUTO_MUTE_DAILY_CAP", "discretion", "record",
    "history", "auto_mutes_since", "may_auto_mute", "auto_mute_decision",
    "active_mutes", "compose_mod_report", "compose_owner_alert",
]
