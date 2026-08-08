"""entitlements.py — ⏳ per-member subscription timers + access entitlements.

Kevin's ask: each account gets a **subscription timer** per purchase (and
bonuses per referral), so anyone can check how much **time** (and, via
referrals, how many bonus **questions**) they have.

Truth model: a member's entitlement is a durable record keyed by their stable
Discord ID (same identity Aria uses everywhere) with a **plan**, the **role**
it maps to, the **source** (stripe | manual | trial | bonus), and an
**expiry timestamp**. Granting while already active **stacks** (adds to the
current expiry) so renewals + bonuses never shorten access. An append-only
history keeps every grant/extend/revoke auditable.

This module owns the store + timer math only. Applying the Discord role +
reading Stripe truth (the auto-confirm reconciler) live elsewhere; until the
Stripe key is vaulted, grants are manual (`/grant`) — the timer works either
way. Bonus **questions** are the referral credits (`referrals.py`); this
module's `compose_status` shows both in one card.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DAY = 86400.0

# plan label → the Discord role it unlocks (matches the shop catalog)
PLAN_ROLES: dict[str, str] = {
    "basic": "Subscriber-Basic",
    "pro": "Subscriber-Pro",
    "vip": "Subscriber-VIP",
    "scout-pass": "Scout-Pass",
    "trial": "Subscriber-Basic",
    # passes-d (Kevin, 2026-07-26): "24 hour pass... week pass, month
    # pass, year pass." One shared all-access role — the entitlement's
    # own `plan` field still distinguishes which pass someone holds.
    "pass-24h": "Pass-Holder",
    "pass-week": "Pass-Holder",
    "pass-month": "Pass-Holder",
    "pass-year": "Pass-Holder",
    # special-passes-d: internal, non-purchasable grants — no Stripe
    # product, no price. Granted by hand via /grant <member> <plan> 36500
    # (100y ≈ permanent, reusing the existing stacking math rather than
    # inventing a separate "permanent" concept).
    "owner-pass": "Owner-Pass",
    "admin-pass": "Admin-Pass",
    "staff-pass": "Support",   # the real staff/employee role, not a parallel one
}


def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "community" / "entitlements"


def _path(data_dir: Path, user_id: str) -> Path:
    uid = "".join(c for c in str(user_id) if c.isdigit()) or "unknown"
    return _dir(data_dir) / f"{uid}.json"


def load(data_dir: Path, user_id: str) -> dict | None:
    try:
        return json.loads(_path(data_dir, user_id).read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write(data_dir: Path, rec: dict) -> None:
    p = _path(data_dir, rec["id"])
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def _blank(user_id: str, now: float) -> dict:
    return {"id": "".join(c for c in str(user_id) if c.isdigit()) or str(user_id),
            "plan": None, "role": None, "source": None,
            "expires_ts": 0.0, "created_ts": now, "history": []}


def _log(rec: dict, action: str, detail: str, now: float) -> None:
    rec.setdefault("history", []).append(
        {"ts": now, "action": action, "detail": detail})


def grant(data_dir: Path, user_id: str, plan: str, days: float, *,
          source: str = "manual", role: str | None = None,
          now: float | None = None) -> dict:
    """Grant/renew a plan for `days`. If the member is still active, the time
    **stacks** onto their current expiry (a renewal never shortens access);
    if lapsed, it starts fresh from now."""
    now = time.time() if now is None else now
    rec = load(data_dir, user_id) or _blank(user_id, now)
    base = max(now, float(rec.get("expires_ts", 0)))     # stack if still active
    rec["expires_ts"] = base + float(days) * DAY
    rec["plan"] = plan
    rec["role"] = role or PLAN_ROLES.get(str(plan).lower())
    rec["source"] = source
    _log(rec, "grant", f"{plan} +{days}d ({source})", now)
    _write(data_dir, rec)
    return rec


def extend_days(data_dir: Path, user_id: str, days: float, *,
                reason: str = "bonus", now: float | None = None) -> dict:
    """Add bonus time (e.g. a referral reward or a make-good) without changing
    the plan. Starts from now if lapsed, else stacks."""
    now = time.time() if now is None else now
    rec = load(data_dir, user_id) or _blank(user_id, now)
    base = max(now, float(rec.get("expires_ts", 0)))
    rec["expires_ts"] = base + float(days) * DAY
    _log(rec, "extend", f"+{days}d ({reason})", now)
    _write(data_dir, rec)
    return rec


def link_stripe(data_dir: Path, user_id: str, customer: str,
                email: str = "", *, now: float | None = None) -> dict:
    """reconciler-d: remember the member's Stripe customer id (set at
    /redeem or first reconcile match) so renewals/cancellations keep the
    timer truthful without asking again."""
    now = time.time() if now is None else now
    rec = load(data_dir, user_id) or _blank(user_id, now)
    rec["customer"] = (customer or "").strip()
    if email:
        rec["email"] = email.strip().lower()
    _log(rec, "link", f"stripe customer {customer[:18]}", now)
    _write(data_dir, rec)
    return rec


def sync_to(data_dir: Path, user_id: str, plan: str, expires_ts: float, *,
            source: str = "stripe", now: float | None = None) -> dict:
    """reconciler-d: set the timer to Stripe truth — MONOTONE (never
    shortens; a shorter provider read leaves the longer local timer
    alone) and idempotent (re-running the reconciler never stacks).
    Shortening happens only through an explicit revoke()."""
    now = time.time() if now is None else now
    rec = load(data_dir, user_id) or _blank(user_id, now)
    new_expiry = max(float(rec.get("expires_ts", 0)), float(expires_ts))
    rec["expires_ts"] = new_expiry
    rec["plan"] = plan
    rec["role"] = PLAN_ROLES.get(str(plan).lower())
    rec["source"] = source
    _log(rec, "sync", f"{plan} → {new_expiry:.0f} ({source})", now)
    _write(data_dir, rec)
    return rec


def revoke(data_dir: Path, user_id: str, reason: str = "",
           now: float | None = None) -> dict | None:
    now = time.time() if now is None else now
    rec = load(data_dir, user_id)
    if rec is None:
        return None
    rec["expires_ts"] = now
    _log(rec, "revoke", reason or "revoked", now)
    _write(data_dir, rec)
    return rec


def is_active(data_dir: Path, user_id: str, *, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    rec = load(data_dir, user_id)
    return bool(rec and float(rec.get("expires_ts", 0)) > now)


def days_left(data_dir: Path, user_id: str, *,
              now: float | None = None) -> float:
    now = time.time() if now is None else now
    rec = load(data_dir, user_id)
    if not rec:
        return 0.0
    return max(0.0, (float(rec.get("expires_ts", 0)) - now) / DAY)


def status(data_dir: Path, user_id: str, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    rec = load(data_dir, user_id) or _blank(user_id, now)
    left = max(0.0, (float(rec.get("expires_ts", 0)) - now) / DAY)
    return {"plan": rec.get("plan"), "role": rec.get("role"),
            "source": rec.get("source"), "active": left > 0,
            "days_left": left, "expires_ts": rec.get("expires_ts", 0)}


def list_all(data_dir: Path) -> list[dict]:
    """Every entitlement record, active or lapsed — the reconciler reads
    lapsed ones too (their stripe links still identify people)."""
    out: list[dict] = []
    try:
        for p in _dir(data_dir).glob("*.json"):
            try:
                out.append(json.loads(p.read_text("utf-8")))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return []
    return out


def list_active(data_dir: Path, *, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    out: list[dict] = []
    try:
        for p in _dir(data_dir).glob("*.json"):
            try:
                rec = json.loads(p.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if float(rec.get("expires_ts", 0)) > now:
                out.append(rec)
    except Exception:  # noqa: BLE001
        return []
    out.sort(key=lambda r: r.get("expires_ts", 0))
    return out


def _fmt_left(days: float) -> str:
    if days <= 0:
        return "expired"
    if days < 1:
        return f"{int(days * 24)}h left"
    return f"{int(days)}d left"


def compose_status(data_dir: Path, user_id: str, *,
                   now: float | None = None) -> str:
    """The member's 'what do I have' card — subscription time + bonus
    questions (referral credits) + referrals, all in one."""
    st = status(data_dir, user_id, now=now)
    lines = ["⏳ **Your access** (private to you)"]
    if st["active"]:
        lines.append(f"• Plan: **{(st['plan'] or 'subscriber').upper()}** · "
                     f"**{_fmt_left(st['days_left'])}** "
                     f"({st['days_left']:.1f} days)")
    else:
        lines.append("• Plan: **none active** — grab one in #storefront to "
                     "unlock your bots. 💛")
    # bonus questions come from referral credits
    try:
        from sovereign_agent import referrals
        credits = referrals.credits_of(data_dir, user_id)
        prof = referrals.ensure_profile(data_dir, user_id)
        lines.append(f"• ✨ Bonus questions: **{credits}** · referrals: "
                     f"**{len(prof.get('referred', []))}** "
                     f"(share `{prof['code']}` for more)")
    except Exception:  # noqa: BLE001
        pass
    lines.append("")
    lines.append("Earn more time-free questions with `/refer`. 💛")
    return "\n".join(lines)


__all__ = [
    "PLAN_ROLES", "DAY", "load", "grant", "extend_days", "revoke",
    "is_active", "days_left", "status", "list_active", "compose_status",
    "link_stripe", "sync_to", "list_all",
]
