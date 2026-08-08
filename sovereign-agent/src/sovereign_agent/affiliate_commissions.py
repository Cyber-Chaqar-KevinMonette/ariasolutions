"""affiliate_commissions.py — close the attribution gap.

Kevin, 2026-07-25: the referral system (`referrals.py`) already tracks
who referred whom (`referred_by`/`referred_at`), already has the 25%-for-
6-months commission math (`MARKETER_PCT`/`MARKETER_MONTHS`), and already
has `record_earning()` to credit a marketer — but nothing anywhere ever
called it. This module is the missing bridge: given a real, verified
purchase (a Stripe charge `sync_verified_income` already confirmed
succeeded/paid/not-refunded), decide whether it earns someone a
commission, and if so, credit it — exactly once per charge, ever.

`record_earning()` itself has zero dedup protection (confirmed: it just
adds to a running total), so THIS module is the single gate that's ever
allowed to call it — the same NDJSON charge-id ledger shape as
`income_ledger.py`, applied to attribution instead of income totals.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

__all__ = ["attribute_commission", "is_attributed"]


def _ledger_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "affiliate_commissions.ndjson"


def _attributed_charge_ids(data_dir: Path | None = None) -> set[str]:
    path = _ledger_path(data_dir)
    if not path.is_file():
        return set()
    out: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.add(json.loads(line)["charge_id"])
            except Exception:  # noqa: BLE001 — one bad line never breaks the read
                continue
    except Exception:  # noqa: BLE001
        return set()
    return out


def is_attributed(charge_id: str, data_dir: Path | None = None) -> bool:
    """Has this exact charge already had its commission attributed?"""
    charge_id = (charge_id or "").strip()
    if not charge_id:
        return False
    return charge_id in _attributed_charge_ids(data_dir)


def _record_attribution(charge_id: str, referrer_id: str, cents: int,
                        data_dir: Path | None = None) -> None:
    path = _ledger_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"charge_id": charge_id, "referrer_id": referrer_id,
                            "cents": cents, "ts": time.time()}) + "\n")


def attribute_commission(
    data_dir: Path, buyer_id: str, amount_cents: int, charge_id: str,
    *, source: str = "stripe", now: float | None = None,
) -> dict | None:
    """A real, verified purchase just happened — does it earn someone a
    commission? Returns the referrals.py record_earning() result if a
    commission was credited, or None if there's nothing to attribute
    (never referred, referrer isn't a marketer, outside the 6-month
    window, or this exact charge was already attributed).

    Idempotent by charge_id: re-running this for the same charge (e.g. a
    repeated Stripe sync) is always a safe no-op the second time — the
    ONLY thing that can ever grow a marketer's `pending_cents` for a given
    charge, once."""
    charge_id = (charge_id or "").strip()
    if not charge_id or amount_cents <= 0:
        return None
    if is_attributed(charge_id, data_dir):
        return None

    from sovereign_agent import referrals

    buyer = referrals.ensure_profile(data_dir, buyer_id)
    referrer_id = buyer.get("referred_by")
    if not referrer_id:
        return None

    referrer = referrals.ensure_profile(data_dir, referrer_id)
    if referrer.get("role") != referrals.ROLE_MARKETER:
        return None

    referred_at = buyer.get("referred_at")
    if not referred_at:
        return None  # no timestamp on record (pre-dates this field) — never assume "forever"
    now = time.time() if now is None else now
    window_seconds = referrals.MARKETER_MONTHS * 30 * 86400
    if now - referred_at > window_seconds:
        return None

    commission_cents = int(amount_cents * referrals.MARKETER_PCT)
    if commission_cents <= 0:
        return None

    result = referrals.record_earning(data_dir, referrer_id, commission_cents, source)
    _record_attribution(charge_id, referrer_id, commission_cents, data_dir)
    return result
