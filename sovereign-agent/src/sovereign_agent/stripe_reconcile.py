"""stripe_reconcile.py — 🔄 the automatic redeem: Stripe truth → timers.

Kevin's ask (2026-07-18): "is there any way to make the redeem system
better or automatic?" Yes — the reconciler. Personalized buy links carry
the buyer's Discord ID (`client_reference_id`), so a purchase
self-identifies; this module turns the whole Stripe book into a small,
conservative action plan the bot applies on a slow background tick.

The financial-integrity doctrine (Kevin: "god tier… no mistakes"):
  • READ-ONLY against Stripe — this module moves no money, ever.
  • Fail-safe toward NOT changing: no data → no actions; unmatched
    subscriptions are REPORTED, never guessed onto a member.
  • Monotone + idempotent: timers only move to provider truth via
    `entitlements.sync_to` (never stack, never shorten); re-running the
    reconciler is always safe.
  • Revoke only with positive evidence: the member is LINKED to a Stripe
    customer AND that customer's subs are all dead AND the entitlement
    came from stripe. Manual/trial/bonus grants are never touched.

Pure: `plan_actions` is data → data; `apply_plan` writes entitlement
records. Roles/DMs/receipts live in the bot (the gateway holds those keys).
"""
from __future__ import annotations

import time
from pathlib import Path

__all__ = ["ALIVE_STATUSES", "plan_actions", "apply_plan",
           "compose_reconcile_report"]

# a subscription in one of these states still deserves access (past_due =
# Stripe's dunning grace — never cut a card hiccup off instantly)
ALIVE_STATUSES = ("active", "trialing", "past_due")


def _digits(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def plan_actions(subs: list[dict], refs: dict[str, str],
                 ents: list[dict], *, now: float | None = None) -> dict:
    """The conservative diff.

    subs — stripe_sync.list_subscriptions() rows
    refs — stripe_sync.checkout_refs(): sub_id → discord id (buy links)
    ents — every entitlement record (entitlements dir), incl. lapsed

    → {"syncs": [{user_id, plan, expires_ts, customer, why}],
       "revokes": [{user_id, why}],
       "unmatched": ["…human lines…"]}
    """
    now = time.time() if now is None else now
    links: dict[str, str] = {}          # customer id → discord id (known)
    for rec in ents:
        cust = (rec.get("customer") or "").strip()
        if cust:
            links[cust] = str(rec.get("id"))

    alive_by_user: dict[str, dict] = {}
    unmatched: list[str] = []
    seen_customers_alive: set[str] = set()
    for sub in subs:
        if sub.get("status") not in ALIVE_STATUSES:
            continue
        seen_customers_alive.add(sub.get("customer") or "")
        uid = _digits(refs.get(sub.get("sub_id", ""), "")) \
            or links.get(sub.get("customer") or "", "")
        if not uid:
            unmatched.append(
                f"{sub.get('plan', '?')} ${sub.get('amount', 0) / 100:.0f}/mo "
                f"({(sub.get('email') or 'no email')[:40]}) — no Discord "
                "link; they can /redeem, or buy links will self-identify")
            continue
        best = alive_by_user.get(uid)
        if best is None or sub.get("expires_ts", 0) > best.get("expires_ts", 0):
            alive_by_user[uid] = sub

    syncs = []
    ents_by_user = {str(r.get("id")): r for r in ents}
    for uid, sub in alive_by_user.items():
        rec = ents_by_user.get(uid) or {}
        cur = float(rec.get("expires_ts", 0) or 0)
        want = float(sub.get("expires_ts", 0) or 0)
        if want > cur + 60:            # only when Stripe truly extends
            syncs.append({"user_id": uid, "plan": sub.get("plan", "basic"),
                          "expires_ts": want,
                          "customer": sub.get("customer", ""),
                          "why": f"stripe {sub.get('status')} through "
                                 + time.strftime("%Y-%m-%d",
                                                 time.localtime(want))})

    revokes = []
    if subs:                            # an empty read NEVER revokes anyone
        for rec in ents:
            uid = str(rec.get("id"))
            cust = (rec.get("customer") or "").strip()
            if (rec.get("source") == "stripe" and cust
                    and float(rec.get("expires_ts", 0)) > now
                    and cust not in seen_customers_alive
                    and uid not in alive_by_user):
                revokes.append({"user_id": uid,
                                "why": "no live subscription on the linked "
                                       "Stripe customer (canceled/ended)"})
    return {"syncs": syncs, "revokes": revokes, "unmatched": unmatched}


def apply_plan(data_dir: Path, actions: dict, *,
               now: float | None = None) -> dict:
    """Write the plan to the entitlement store (monotone sync_to +
    explicit revoke). Returns honest per-user receipts; roles/DMs are the
    bot's half."""
    from sovereign_agent import entitlements
    now = time.time() if now is None else now
    receipts = {"synced": [], "revoked": []}
    for a in actions.get("syncs", []):
        entitlements.sync_to(data_dir, a["user_id"], a["plan"],
                             a["expires_ts"], source="stripe", now=now)
        if a.get("customer"):
            entitlements.link_stripe(data_dir, a["user_id"], a["customer"],
                                     now=now)
        receipts["synced"].append(a)
    for a in actions.get("revokes", []):
        entitlements.revoke(data_dir, a["user_id"], a["why"], now=now)
        receipts["revoked"].append(a)
    return receipts


def compose_reconcile_report(actions: dict, receipts: dict | None = None) -> str:
    """The #payout-log line — honest, specific, calm when quiet."""
    n_s, n_r = len(actions.get("syncs", [])), len(actions.get("revokes", []))
    n_u = len(actions.get("unmatched", []))
    if not (n_s or n_r or n_u):
        return ("🔄 Stripe reconcile: everything already matches — "
                "timers are truthful.")
    lines = ["🔄 Stripe reconcile:"]
    for a in actions.get("syncs", []):
        lines.append(f"  ✓ <@{a['user_id']}> → {a['plan'].upper()} "
                     f"({a['why']})")
    for a in actions.get("revokes", []):
        lines.append(f"  − <@{a['user_id']}> timer ended — {a['why']}")
    for u in actions.get("unmatched", [])[:5]:
        lines.append(f"  ? unmatched: {u}")
    if n_u > 5:
        lines.append(f"  … +{n_u - 5} more unmatched")
    return "\n".join(lines)
