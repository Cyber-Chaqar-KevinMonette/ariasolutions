"""redemption_queue.py — 🧾 who needs redeeming, what they get, and WHEN.

Kevin's ask (2026-07-18): "a list of people who need to redeem and how
much time they get and bonus questions. Then automatically redeem for
them every time the list is above 0 — unless she is mid task; then the
redemption must wait until her task is uninterrupted and finished.
Nothing must conflict and everything must wait their turn."

Three pieces, all pure:
  • the LIST — composed from the reconciler's conservative diff
    (stripe_reconcile.plan_actions): each row = who, plan, days of time,
    and their bonus-question credits (referrals.credits_of).
  • the GATE — `is_mid_task()`: True while a work session is genuinely
    running (status=active AND freshly updated — a crashed session's
    stale 'active' never blocks redemptions forever). The reconciler
    defers while she works and retries soon after; her focus is never
    interrupted, the members never wait longer than her task.
  • the RENDER — the owner-readable list (/redemptions, #payout-log).

The wait-your-turn doctrine holds end to end: this gate (her task first)
→ _admin_lock (setup ops take turns) → _SEND_PACE_S (Discord's limits).
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

__all__ = ["is_mid_task", "build_list", "compose_redemption_list",
           "FRESH_S"]

FRESH_S = 600.0     # an 'active' session updated within 10 min = truly working


def _age_s(iso: str, now: float) -> float:
    try:
        return max(0.0, now - datetime.fromisoformat(iso).timestamp())
    except Exception:  # noqa: BLE001
        return float("inf")            # unreadable timestamp = stale


def is_mid_task(data_dir: Path | None = None, *,
                now: float | None = None,
                fresh_s: float = FRESH_S) -> bool:
    """Is Aria in the middle of a cockpit work session right now?
    True only for a FRESH active session; stale actives (crash leftovers)
    don't count. Any read failure → False (redemptions proceed —
    fail-open here is right: a broken gate must not strand members)."""
    now = time.time() if now is None else now
    try:
        from sovereign_agent.agent_session import SessionStore
        store = SessionStore(root=(Path(data_dir) / "sessions")
                             if data_dir is not None else None)
        for s in store.list_all(status="active"):
            if _age_s(str(getattr(s, "updated_at", "")), now) <= fresh_s:
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


def build_list(actions: dict, data_dir: Path | None = None,
               *, now: float | None = None) -> list[dict]:
    """The redemption list from a reconciler diff: one row per member —
    {user_id, plan, days (time they get), bonus_questions (their referral
    credits)}. Unmatched subscriptions ride along as human lines."""
    now = time.time() if now is None else now
    rows = []
    for a in (actions or {}).get("syncs", []):
        days = max(0.0, (float(a.get("expires_ts", 0)) - now) / 86400.0)
        credits = 0
        try:
            from sovereign_agent.referrals import credits_of
            credits = int(credits_of(data_dir, str(a.get("user_id"))))
        except Exception:  # noqa: BLE001
            pass
        rows.append({"user_id": str(a.get("user_id")),
                     "plan": str(a.get("plan", "basic")),
                     "days": round(days, 1),
                     "bonus_questions": credits})
    return rows


def compose_redemption_list(actions: dict, data_dir: Path | None = None,
                            *, mid_task: bool | None = None,
                            now: float | None = None) -> str:
    """The owner view: who's owed, what they get, and whether the queue
    is flowing or politely waiting on her task."""
    rows = build_list(actions, data_dir, now=now)
    unmatched = (actions or {}).get("unmatched", [])
    lines = ["🧾 Redemption queue"]
    if mid_task is True:
        lines.append("  ⏸ holding — she's mid-task; redemptions run the "
                     "moment her work finishes (nothing conflicts).")
    elif mid_task is False:
        lines.append("  ▶ clear to flow — processed automatically.")
    if not rows and not unmatched:
        lines.append("  ✨ empty — everyone who paid is redeemed and "
                     "timered. Nothing owed.")
        return "\n".join(lines)
    for r in rows:
        lines.append(f"  • <@{r['user_id']}> → {r['plan'].upper()}: "
                     f"+{r['days']:.0f} days of time · "
                     f"{r['bonus_questions']} bonus question(s) banked")
    for u in unmatched[:5]:
        lines.append(f"  ? can't auto-redeem yet: {u}")
    if len(unmatched) > 5:
        lines.append(f"  … +{len(unmatched) - 5} more unlinked")
    return "\n".join(lines)
