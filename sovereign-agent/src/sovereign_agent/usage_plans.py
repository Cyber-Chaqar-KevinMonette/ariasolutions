"""usage_plans.py — 📊 usage like a real AI company (Kevin, 2026-07-18).

"Change our usage system to be more like normal AI companies." The shape
every major AI product uses, mapped onto the shop:

  • **Plan-tiered daily quotas** — your subscription sets how many LIVE
    (LLM) answers you get per day. Deterministic answers (catalog, status,
    weather) stay free and unlimited — like cached/basic responses.
  • **Daily reset** — quotas reset at local midnight, every day.
  • **Top-ups** — ✨ referral credits work like pay-as-you-go credits:
    one credit = one extra live answer past your daily quota.
  • **The upgrade path** — hit the wall and she tells you plainly what
    plan lifts it (#storefront), like every provider's limit banner.
  • The 15s per-person cooldown + global per-minute cap stay — that's
    the industry's RPM layer; this module is the daily-quota layer.

Durable per-user day counters: `<data>/ask_usage/<user_id>.json`
{"day": "YYYY-MM-DD", "used": N}. Atomic, corrupt→fresh, never raises.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

__all__ = ["PLAN_QUOTAS", "FREE_QUOTA", "quota_for", "used_today",
           "try_consume", "usage_state", "compose_usage"]

# live answers per day, by plan — free tier is real but small, exactly
# like a normal AI company's free tier
FREE_QUOTA = 5
PLAN_QUOTAS: dict[str, int] = {
    "trial": 10,
    "basic": 25,
    "scout-pass": 40,
    "pro": 60,
    "vip": 150,
    # passes-d (Kevin, 2026-07-26): all-access passes match VIP's quota —
    # same tier, sold by duration instead of a monthly commitment.
    "pass-24h": 150,
    "pass-week": 150,
    "pass-month": 150,
    "pass-year": 150,
    # special-passes-d: staff/admin get VIP-equivalent quota; owner is
    # effectively unlimited — this is also the fix for a real gap found
    # while designing passes: try_consume() had NO owner bypass, so Kevin
    # himself was subject to the 5/day free quota unless he happened to
    # hold an active plan. Granting an owner-pass entitlement (once, via
    # /grant) closes that using the existing mechanism, no new bypass
    # code needed.
    "admin-pass": 150,
    "staff-pass": 150,
    "owner-pass": 999999,
}


def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _path(data_dir: Path, user_id: str) -> Path:
    uid = "".join(c for c in str(user_id) if c.isalnum()) or "anon"
    return Path(data_dir) / "ask_usage" / f"{uid}.json"


def _load(data_dir: Path, user_id: str, now: float) -> dict:
    try:
        rec = json.loads(_path(data_dir, user_id).read_text(encoding="utf-8"))
        if isinstance(rec, dict) and rec.get("day") == _day(now):
            return {"day": rec["day"], "used": int(rec.get("used", 0))}
    except Exception:  # noqa: BLE001
        pass
    return {"day": _day(now), "used": 0}          # new day = fresh quota


def _write(data_dir: Path, user_id: str, rec: dict) -> None:
    p = _path(data_dir, user_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def quota_for(data_dir: Path | None, user_id: str, *,
              now: float | None = None) -> int:
    """The member's daily live-answer quota, from their ACTIVE plan.
    Lapsed or no plan → the free tier."""
    now = time.time() if now is None else now
    try:
        from sovereign_agent.entitlements import status
        st = status(data_dir, str(user_id), now=now)
        if st.get("active"):
            return PLAN_QUOTAS.get(str(st.get("plan", "")).lower(),
                                   FREE_QUOTA)
    except Exception:  # noqa: BLE001
        pass
    return FREE_QUOTA


def used_today(data_dir: Path, user_id: str, *,
               now: float | None = None) -> int:
    now = time.time() if now is None else now
    return _load(data_dir, user_id, now)["used"]


def try_consume(data_dir: Path | None, user_id: str, *,
                now: float | None = None) -> bool:
    """Spend one live answer from today's quota. True = within quota
    (counted); False = the daily wall (nothing counted). No data_dir →
    allow (never brick her voice over a missing path)."""
    if data_dir is None:
        return True
    now = time.time() if now is None else now
    rec = _load(data_dir, user_id, now)
    if rec["used"] >= quota_for(data_dir, user_id, now=now):
        return False
    rec["used"] += 1
    _write(data_dir, user_id, rec)
    return True


def usage_state(data_dir: Path, user_id: str, *,
                now: float | None = None) -> dict:
    now = time.time() if now is None else now
    quota = quota_for(data_dir, user_id, now=now)
    used = used_today(data_dir, user_id, now=now)
    credits = 0
    plan = "free"
    try:
        from sovereign_agent.entitlements import status
        st = status(data_dir, str(user_id), now=now)
        if st.get("active"):
            plan = str(st.get("plan") or "free")
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.referrals import credits_of
        credits = int(credits_of(data_dir, str(user_id)))
    except Exception:  # noqa: BLE001
        pass
    return {"plan": plan, "quota": quota, "used": used,
            "left": max(0, quota - used), "credits": credits}


def compose_usage(data_dir: Path, user_id: str, *,
                  now: float | None = None) -> str:
    """The /usage card — the meter every AI product shows."""
    s = usage_state(data_dir, user_id, now=now)
    bar_n = 10
    filled = min(bar_n, round(bar_n * s["used"] / s["quota"])) \
        if s["quota"] else bar_n
    bar = "▰" * filled + "▱" * (bar_n - filled)
    lines = [
        "📊 **Your usage today**",
        f"plan: **{s['plan'].upper()}** · live answers: "
        f"{s['used']}/{s['quota']}  {bar}",
        f"✨ credits banked: {s['credits']} (each = 1 extra answer — "
        "earn more with `/refer`)",
        "resets at midnight · catalog/status/weather answers are always "
        "free + unlimited",
    ]
    if s["left"] == 0:
        lines.append("⤴ want a bigger day? plans in #storefront lift the "
                     "quota (Basic 25 · Pro 60 · VIP 150). 💛")
    return "\n".join(lines)
