"""stripe_sync.py — 💳 confirm a purchase from Stripe truth (read-only).

Answers Kevin's question — "how does the bot confirm a person made a purchase,
and *what* they bought?" — using the vaulted `STRIPE_SECRET_KEY` over raw
HTTPS (same pattern as `credentials.probe_stripe_key`; the key is never
logged). A member who paid via a Payment Link runs `/redeem <email>`; we:

  1. find their Stripe **customer** by that email,
  2. read their **active subscription**,
  3. map the price **amount** → our plan (basic/pro/vip/scout-pass),
  4. take the subscription's **current_period_end** as the timer expiry.

The Discord ID ↔ Stripe customer link is stored, so a later reconciler can
keep the timer truthful on renewals/cancellations without asking again.

Pure + injectable-opener tested: no network in tests. Applying the Discord
role + the `/redeem` command live in `discord_admin/bot.py`.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode

_API = "https://api.stripe.com/v1"

# monthly price (cents) → our plan label. Robust to product renames; if an
# amount isn't recognised we still grant generic subscriber access.
AMOUNT_PLAN: dict[int, str] = {
    500: "basic", 1200: "pro", 2500: "vip", 1800: "scout-pass",
}

# passes-d (Kevin, 2026-07-26): the one-time-charge sibling of AMOUNT_PLAN
# (which only ever describes recurring SUBSCRIPTION prices). A pass is
# inherently one-time — there's no subscription `current_period_end` to
# read an expiry from — so each price maps straight to (plan, days) here
# instead. Same "robust to renames" philosophy: an unrecognized one-time
# amount just isn't a pass purchase, nothing breaks.
PASS_PLANS: dict[int, tuple[str, float]] = {
    300: ("pass-24h", 1.0),
    900: ("pass-week", 7.0),
    1900: ("pass-month", 30.0),
    14900: ("pass-year", 365.0),
}


def _default_opener(url, headers, timeout):  # pragma: no cover — real network
    from urllib.request import Request, urlopen
    return urlopen(Request(url, headers=headers), timeout=timeout)


def _get(opener, url: str, key: str, timeout: float) -> dict:
    headers = {"Authorization": f"Bearer {key}",
               "User-Agent": "sovereign-agent-stripe-sync/1.0"}
    with opener(url, headers, timeout) as resp:
        body = resp.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    try:
        return json.loads(body) or {}
    except Exception:  # noqa: BLE001
        return {}


def find_customer(opener, key: str, email: str, *,
                  timeout: float = 10.0) -> str | None:
    q = urlencode({"email": (email or "").strip(), "limit": 1})
    data = _get(opener, f"{_API}/customers?{q}", key, timeout)
    rows = data.get("data") or []
    return rows[0].get("id") if rows else None


def active_subscription(opener, key: str, customer_id: str, *,
                        timeout: float = 10.0) -> dict | None:
    """The customer's active subscription → {amount, plan, expires_ts,
    product} (or None). Reads the first active/trialing sub."""
    q = urlencode({"customer": customer_id, "status": "all", "limit": 10})
    data = _get(opener, f"{_API}/subscriptions?{q}", key, timeout)
    for sub in data.get("data") or []:
        if sub.get("status") not in ("active", "trialing", "past_due"):
            continue
        items = ((sub.get("items") or {}).get("data")) or []
        price = (items[0].get("price") if items else {}) or {}
        amount = int(price.get("unit_amount") or 0)
        return {"amount": amount,
                "plan": AMOUNT_PLAN.get(amount, "basic"),
                "expires_ts": float(sub.get("current_period_end") or 0),
                "status": sub.get("status"),
                "product": price.get("product") or ""}
    return None


def confirm_purchase(opener, key: str, email: str, *,
                     timeout: float = 10.0) -> dict:
    """The full check → {found, active, plan, expires_ts, customer, detail}.
    Never raises; a network/auth problem returns found=False + a reason."""
    email = (email or "").strip()
    if not email or "@" not in email:
        return {"found": False, "active": False,
                "detail": "that doesn't look like an email address"}
    if not (key or "").strip():
        return {"found": False, "active": False,
                "detail": "Stripe isn't configured yet (no secret key)"}
    try:
        cid = find_customer(opener, key, email, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        return {"found": False, "active": False,
                "detail": ("Stripe key rejected (roll it)" if code == 401
                           else f"couldn't reach Stripe ({code or type(exc).__name__})")}
    if not cid:
        return {"found": False, "active": False,
                "detail": ("no Stripe customer with that email — use the exact "
                           "email you paid with, or ask an admin in #order-here")}
    sub = None
    try:
        sub = active_subscription(opener, key, cid, timeout=timeout)
    except Exception:  # noqa: BLE001
        sub = None
    if not sub:
        return {"found": True, "active": False, "customer": cid,
                "detail": "found your account, but no active subscription on it"}
    return {"found": True, "active": True, "customer": cid,
            "plan": sub["plan"], "amount": sub["amount"],
            "expires_ts": sub["expires_ts"], "status": sub["status"],
            "detail": "confirmed"}


# ── reconciler-d (Kevin, 2026-07-18): the whole-book reads ──────────────────
def list_subscriptions(opener, key: str, *, timeout: float = 10.0,
                       limit: int = 100) -> list[dict]:
    """Every subscription on the account (any status), customer expanded →
    [{sub_id, customer, email, status, plan, amount, expires_ts}].
    Read-only; empty list on any failure (the reconciler then does nothing
    — fail-safe toward NOT changing entitlements)."""
    q = urlencode({"status": "all", "limit": limit})
    try:
        data = _get(opener, f"{_API}/subscriptions?{q}&expand[]=data.customer",
                    key, timeout)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for sub in data.get("data") or []:
        cust = sub.get("customer")
        cust_id, email = "", ""
        if isinstance(cust, dict):
            cust_id = cust.get("id") or ""
            email = (cust.get("email") or "").strip().lower()
        elif isinstance(cust, str):
            cust_id = cust
        items = ((sub.get("items") or {}).get("data")) or []
        price = (items[0].get("price") if items else {}) or {}
        amount = int(price.get("unit_amount") or 0)
        out.append({"sub_id": sub.get("id") or "",
                    "customer": cust_id, "email": email,
                    "status": sub.get("status") or "",
                    "plan": AMOUNT_PLAN.get(amount, "basic"),
                    "amount": amount,
                    "expires_ts": float(sub.get("current_period_end") or 0)})
    return out


# ── income-ledger-d (Kevin, 2026-07-25): "make income earned a real
# metric too, but only updates on verified income received" ────────────────
def sync_verified_income(opener, key: str, *, data_dir=None,
                         timeout: float = 10.0, limit: int = 100) -> dict:
    """Pull recent charges from Stripe truth and ledger every REAL
    succeeded one — never a subscription's "active" status (which can be
    true with no fresh charge, or stay true briefly after a charge fails/
    disputes). `income_ledger.record_income` de-duplicates by charge id,
    so calling this repeatedly (a cron tick, a manual /income sync) is
    always safe — a charge is counted exactly once no matter how many
    times it's re-polled. Also attributes marketer commissions
    (affiliate_commissions.attribute_commission) for any charge whose
    buyer was referred by a marketer — resolved via the SAME checkout-
    session client_reference_id machinery `confirm_purchase` already
    uses for buyer identification, reused here for attribution instead
    of duplicated. A commission-attribution failure never blocks the
    income sync itself — best-effort, logged via the return detail only
    when it's the income sync itself that failed.

    passes-d (Kevin, 2026-07-26): the SAME buyer resolution also grants a
    time-boxed entitlement (entitlements.grant) for any charge whose
    amount matches PASS_PLANS — a one-time Payment Link purchase (a
    "pass") has no subscription to reconcile the way Basic/Pro/VIP do,
    so this charge-reading loop is where a pass purchase actually
    becomes access. This module stays Discord-free by design (see the
    module docstring) — it only writes the entitlement record; applying
    the Discord role happens in discord_admin/bot.py's own reconcile
    loop, which reads the returned pass_grants list. A pass-grant
    failure never blocks the income sync itself, same discipline as
    commission attribution.

    Returns {synced, total_cents, detail, pass_grants}; never raises — a
    Stripe/network failure just syncs nothing this round."""
    from sovereign_agent import income_ledger

    if not (key or "").strip():
        return {"synced": 0, "total_cents": income_ledger.total_income_cents(data_dir),
                "detail": "Stripe isn't configured yet (no secret key)",
                "pass_grants": []}
    q = urlencode({"limit": limit, "expand[]": "data.invoice.subscription"})
    try:
        data = _get(opener, f"{_API}/charges?{q}", key, timeout)
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        return {"synced": 0, "total_cents": income_ledger.total_income_cents(data_dir),
                "detail": ("Stripe key rejected (roll it)" if code == 401
                           else f"couldn't reach Stripe ({code or type(exc).__name__})"),
                "pass_grants": []}
    try:
        by_subscription = checkout_refs(opener, key, timeout=timeout)
        by_payment_intent = checkout_refs_by_payment_intent(opener, key, timeout=timeout)
    except Exception:  # noqa: BLE001 — attribution is best-effort, income sync isn't
        by_subscription, by_payment_intent = {}, {}
    synced = 0
    pass_grants: list[dict] = []
    for charge in data.get("data") or []:
        # VERIFIED means Stripe itself says the money actually landed —
        # succeeded AND paid AND not refunded. A pending/failed/refunded
        # charge is never income, however "active" its subscription looks.
        if charge.get("status") != "succeeded":
            continue
        if not charge.get("paid"):
            continue
        if charge.get("refunded"):
            continue
        charge_id = charge.get("id") or ""
        amount = int(charge.get("amount") or 0)
        if not charge_id or amount <= 0:
            continue
        recorded = income_ledger.record_income(
            charge_id, amount, source="stripe",
            note=(charge.get("description") or "")[:200], data_dir=data_dir,
        )
        if recorded is not None:
            synced += 1
        try:
            buyer_id = _buyer_for_charge(charge, by_subscription, by_payment_intent)
            if buyer_id:
                attr_dir = data_dir
                if attr_dir is None:
                    from sovereign_agent.config import SETTINGS
                    attr_dir = SETTINGS.paths.data_dir
                try:
                    from sovereign_agent.affiliate_commissions import attribute_commission
                    attribute_commission(attr_dir, buyer_id, amount, charge_id,
                                         source="stripe")
                except Exception:  # noqa: BLE001 — attribution must never break the income sync
                    pass
                # passes-d: only grant once — recorded is None on a
                # re-poll of an already-ledgered charge (record_income's
                # own dedup-by-charge-id), the natural idempotency guard
                # so a repeat sync can never re-grant/stack the same
                # purchase's days twice.
                pass_plan = PASS_PLANS.get(amount)
                if recorded is not None and pass_plan:
                    try:
                        from sovereign_agent import entitlements
                        plan, days = pass_plan
                        entitlements.grant(attr_dir, buyer_id, plan, days,
                                          source="stripe")
                        pass_grants.append({"user_id": buyer_id, "plan": plan,
                                            "days": days})
                    except Exception:  # noqa: BLE001 — a pass-grant failure must never break income sync
                        pass
        except Exception:  # noqa: BLE001 — attribution must never break the income sync
            pass
    return {"synced": synced, "total_cents": income_ledger.total_income_cents(data_dir),
            "detail": "ok", "pass_grants": pass_grants}


def checkout_refs(opener, key: str, *, timeout: float = 10.0,
                  limit: int = 100) -> dict[str, str]:
    """subscription_id → client_reference_id, from Payment-Link checkout
    sessions. Personalized buy links carry the buyer's Discord ID here —
    the zero-typing purchase↔person map. Empty dict on failure."""
    q = urlencode({"limit": limit})
    try:
        data = _get(opener, f"{_API}/checkout/sessions?{q}", key, timeout)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for s in data.get("data") or []:
        ref = (s.get("client_reference_id") or "").strip()
        sub = s.get("subscription")
        if ref and isinstance(sub, str) and sub:
            out[sub] = ref
    return out


# affiliate-commissions-d (Kevin, 2026-07-25): checkout_refs() only ever
# keyed by subscription_id, which resolves the buyer for a subscription's
# FIRST charge (the one the checkout session itself produced) but not
# recurring renewal charges, and never resolves a one-time purchase at
# all (no subscription exists). This is the other half — same source
# data (checkout sessions), keyed by payment_intent instead, which every
# charge (one-time or subscription) carries.
def checkout_refs_by_payment_intent(opener, key: str, *, timeout: float = 10.0,
                                    limit: int = 100) -> dict[str, str]:
    """payment_intent_id → client_reference_id, from the same Payment-Link
    checkout sessions. Empty dict on failure."""
    q = urlencode({"limit": limit})
    try:
        data = _get(opener, f"{_API}/checkout/sessions?{q}", key, timeout)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for s in data.get("data") or []:
        ref = (s.get("client_reference_id") or "").strip()
        pi = s.get("payment_intent")
        if ref and isinstance(pi, str) and pi:
            out[pi] = ref
    return out


def _buyer_for_charge(charge: dict, by_subscription: dict[str, str],
                      by_payment_intent: dict[str, str]) -> str:
    """Resolve a charge to the Discord ID that bought it, if any. Tries
    the subscription link first (covers renewals via an expanded
    invoice.subscription), then the payment_intent link (covers one-time
    purchases and a subscription's own first charge)."""
    invoice = charge.get("invoice")
    if isinstance(invoice, dict):
        sub = invoice.get("subscription")
        sub_id = sub.get("id") if isinstance(sub, dict) else sub
        if isinstance(sub_id, str) and sub_id in by_subscription:
            return by_subscription[sub_id]
    pi = charge.get("payment_intent")
    if isinstance(pi, str) and pi in by_payment_intent:
        return by_payment_intent[pi]
    return ""


def buy_url(url: str, discord_id: str) -> str:
    """A member's personalized Payment Link — the same link with their
    Discord ID as client_reference_id, so the purchase self-identifies."""
    url = (url or "").strip()
    uid = "".join(c for c in str(discord_id) if c.isdigit())
    if not url or not uid:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}client_reference_id={uid}"


__all__ = ["AMOUNT_PLAN", "PASS_PLANS", "find_customer", "active_subscription",
           "confirm_purchase", "list_subscriptions", "checkout_refs",
           "checkout_refs_by_payment_intent", "sync_verified_income",
           "buy_url"]
