"""payouts.py — the other half referrals.py's own docstring pointed to.

Kevin, 2026-07-25: fully automated payouts for marketer commissions, via
Stripe Connect Express. A marketer completes Stripe's own hosted
onboarding (Stripe's KYC, not custom-built here) before any money can
reach them; `run_payouts()` then transfers real, already-earned
`pending_cents` to their connected account, above a minimum threshold so
tiny balances don't generate needless transfer fees.

Firing `run_payouts()` is still an explicit human action (`/payout run`,
owner-only, Tier-3-gated like every other money-moving action in this
codebase) — the automation is in the MECHANISM (real Stripe transfers,
no manual per-person sending), not in removing the human from the loop
entirely. Matches this project's standing "propose, human decides"
doctrine for anything touching real money.

Tax note: Stripe Connect Express, with the platform account's tax-
reporting setting enabled (a one-time Stripe Dashboard configuration, NOT
code), automatically generates and files 1099-NEC/1099-K forms for
connected accounts crossing the IRS $600/yr threshold. That dashboard
setting is a real prerequisite for this being a sound choice — noted
here, not something this module can verify or enable.

Same injectable-opener, no-network-in-tests discipline as every function
in stripe_sync.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

_API = "https://api.stripe.com/v1"

__all__ = [
    "create_connect_account", "onboarding_link_for", "account_status",
    "run_payouts", "connect_account_for",
]


def _default_opener(url, headers, body, timeout):  # pragma: no cover — real network
    from urllib.request import Request, urlopen
    data = urlencode(body).encode() if body else None
    return urlopen(Request(url, data=data, headers=headers, method="POST"
                          if body is not None else "GET"), timeout=timeout)


def _post(opener, url: str, key: str, timeout: float, *,
         body: dict | None = None, idempotency_key: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}",
               "User-Agent": "sovereign-agent-payouts/1.0"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    with opener(url, headers, body or {}, timeout) as resp:
        raw = resp.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        return json.loads(raw) or {}
    except Exception:  # noqa: BLE001
        return {}


def _get(opener, url: str, key: str, timeout: float) -> dict:
    headers = {"Authorization": f"Bearer {key}",
               "User-Agent": "sovereign-agent-payouts/1.0"}
    with opener(url, headers, None, timeout) as resp:
        raw = resp.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        return json.loads(raw) or {}
    except Exception:  # noqa: BLE001
        return {}


# ── the marketer_id -> Stripe Connect account_id mapping ────────────────────
def _accounts_path(data_dir: Path) -> Path:
    return Path(data_dir) / "connect_accounts.json"


def _load_accounts(data_dir: Path) -> dict[str, str]:
    try:
        data = json.loads(_accounts_path(data_dir).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_accounts(data_dir: Path, accounts: dict[str, str]) -> None:
    p = _accounts_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(accounts, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def connect_account_for(marketer_id: str, data_dir: Path) -> str | None:
    """The marketer's Stripe Connect account id, if one's been created."""
    return _load_accounts(data_dir).get(marketer_id)


def create_connect_account(opener, key: str, marketer_id: str, *,
                           data_dir: Path, timeout: float = 10.0) -> dict:
    """Create (or return the existing) Stripe Connect Express account for
    this marketer — idempotent per marketer_id, never creates a second
    account for someone who already has one. Real KYC/onboarding happens
    on Stripe's own hosted flow, not here."""
    existing = connect_account_for(marketer_id, data_dir)
    if existing:
        return {"account_id": existing, "created": False}
    result = _post(opener, f"{_API}/accounts", key, timeout,
                  body={"type": "express"})
    account_id = result.get("id") or ""
    if not account_id:
        return {"account_id": "", "created": False, "error": result}
    accounts = _load_accounts(data_dir)
    accounts[marketer_id] = account_id
    _save_accounts(data_dir, accounts)
    return {"account_id": account_id, "created": True}


def onboarding_link_for(opener, key: str, account_id: str, *,
                        refresh_url: str, return_url: str,
                        timeout: float = 10.0) -> str:
    """A one-time-use URL to Stripe's own hosted Connect Express
    onboarding for this account. Empty string on failure."""
    result = _post(opener, f"{_API}/account_links", key, timeout, body={
        "account": account_id, "refresh_url": refresh_url,
        "return_url": return_url, "type": "account_onboarding",
    })
    return result.get("url") or ""


def account_status(opener, key: str, account_id: str, *,
                   timeout: float = 10.0) -> dict:
    """{payouts_enabled, detail} — whether Stripe's own onboarding/KYC is
    complete enough to actually receive a transfer. Never raises; a
    lookup failure reads as not-ready, never as ready."""
    try:
        data = _get(opener, f"{_API}/accounts/{account_id}", key, timeout)
    except Exception as exc:  # noqa: BLE001
        return {"payouts_enabled": False, "detail": type(exc).__name__}
    return {"payouts_enabled": bool(data.get("payouts_enabled")), "detail": "ok"}


def run_payouts(data_dir: Path, opener, key: str, *,
                min_cents: int = 2500, timeout: float = 10.0) -> dict:
    """The one thing that actually moves real money. For every marketer
    with pending_cents >= min_cents and a Connect account whose Stripe
    onboarding is complete (payouts_enabled), issues a real Transfer, then
    moves pending -> paid (referrals.mark_paid, itself idempotent by
    transfer id). A Stripe Idempotency-Key (marketer + pending amount +
    day) means an accidental double /payout run within the same day
    resolves to the SAME transfer at Stripe's own layer, never a second
    real payment. Returns {paid: [...], skipped: [...], total_cents}."""
    from sovereign_agent import referrals
    import time as _time

    paid: list[dict] = []
    skipped: list[dict] = []
    if not (key or "").strip():
        return {"paid": paid, "skipped": skipped, "total_cents": 0,
                "detail": "Stripe isn't configured yet (no secret key)"}

    day = _time.strftime("%Y-%m-%d", _time.gmtime())
    for rec in referrals.list_profiles(data_dir):
        if rec.get("role") != referrals.ROLE_MARKETER:
            continue
        cents = int(rec.get("pending_cents", 0))
        marketer_id = rec["id"]
        if cents < min_cents:
            skipped.append({"marketer": marketer_id, "reason": "below minimum"})
            continue
        account_id = connect_account_for(marketer_id, data_dir)
        if not account_id:
            skipped.append({"marketer": marketer_id, "reason": "no Connect account"})
            continue
        try:
            status = account_status(opener, key, account_id, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"marketer": marketer_id,
                            "reason": f"status check failed: {type(exc).__name__}"})
            continue
        if not status.get("payouts_enabled"):
            skipped.append({"marketer": marketer_id,
                            "reason": "Connect onboarding incomplete"})
            continue
        idem_key = f"payout:{marketer_id}:{cents}:{day}"
        try:
            transfer = _post(opener, f"{_API}/transfers", key, timeout, body={
                "amount": cents, "currency": "usd", "destination": account_id,
            }, idempotency_key=idem_key)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"marketer": marketer_id,
                            "reason": f"transfer failed: {type(exc).__name__}"})
            continue
        transfer_id = transfer.get("id") or ""
        if not transfer_id:
            skipped.append({"marketer": marketer_id,
                            "reason": f"transfer response had no id: {transfer}"})
            continue
        referrals.mark_paid(data_dir, marketer_id, cents, transfer_id=transfer_id)
        paid.append({"marketer": marketer_id, "cents": cents,
                    "transfer_id": transfer_id})
    return {"paid": paid, "skipped": skipped,
            "total_cents": sum(p["cents"] for p in paid), "detail": "ok"}
