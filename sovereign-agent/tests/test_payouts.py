"""Tests for payouts.py — Stripe Connect Express, fully automated payouts.

Kevin, 2026-07-25: chose fully automated payouts for marketer commissions.
The automation is in the MECHANISM (real Stripe transfers) — firing
`run_payouts()` is still an explicit human action (/payout run, owner-
gated). Same injectable-opener, no-network-in-tests discipline as
stripe_sync.py.
"""
from __future__ import annotations

import json

from sovereign_agent import payouts as po
from sovereign_agent import referrals as rf


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener_for(routes):
    """routes: list of (substring, payload) matched against the URL, in
    order. Records every call for assertion."""
    calls = []

    def opener(url, headers, body, timeout):
        calls.append({"url": url, "headers": headers, "body": body})
        for frag, payload in routes:
            if frag in url:
                return _Resp(payload)
        return _Resp({})
    opener.calls = calls
    return opener


def _make_marketer(tmp_path, marketer_id, pending_cents):
    rf.ensure_profile(tmp_path, marketer_id)
    rf.set_marketer(tmp_path, marketer_id, on=True)
    if pending_cents:
        rf.record_earning(tmp_path, marketer_id, pending_cents, "stripe")


# ── connect account creation ─────────────────────────────────────────────────
def test_create_connect_account_is_idempotent(tmp_path):
    opener = _opener_for([("/accounts", {"id": "acct_1"})])
    first = po.create_connect_account(opener, "sk_test", "900100001", data_dir=tmp_path)
    second = po.create_connect_account(opener, "sk_test", "900100001", data_dir=tmp_path)
    assert first == {"account_id": "acct_1", "created": True}
    assert second == {"account_id": "acct_1", "created": False}
    assert len(opener.calls) == 1  # no second Stripe call once it exists
    assert po.connect_account_for("900100001", tmp_path) == "acct_1"


def test_onboarding_link_for_returns_the_url():
    opener = _opener_for([("/account_links", {"url": "https://connect.stripe.com/setup/xyz"})])
    url = po.onboarding_link_for(opener, "sk_test", "acct_1",
                                 refresh_url="https://x/refresh",
                                 return_url="https://x/return")
    assert url == "https://connect.stripe.com/setup/xyz"


def test_account_status_reads_payouts_enabled():
    opener = _opener_for([("/accounts/acct_1", {"payouts_enabled": True})])
    status = po.account_status(opener, "sk_test", "acct_1")
    assert status["payouts_enabled"] is True


def test_account_status_never_raises_on_failure():
    def opener(url, headers, body, timeout):
        raise RuntimeError("boom")
    status = po.account_status(opener, "sk_test", "acct_1")
    assert status["payouts_enabled"] is False


# ── run_payouts ───────────────────────────────────────────────────────────
def test_run_payouts_transfers_and_marks_paid(tmp_path):
    _make_marketer(tmp_path, "900100001", 5000)
    po._save_accounts(tmp_path, {"900100001": "acct_1"})
    opener = _opener_for([
        ("/accounts/acct_1", {"payouts_enabled": True}),
        ("/transfers", {"id": "tr_1"}),
    ])
    result = po.run_payouts(tmp_path, opener, "sk_test")
    assert result["paid"] == [{"marketer": "900100001", "cents": 5000, "transfer_id": "tr_1"}]
    assert result["total_cents"] == 5000
    rec = rf.ensure_profile(tmp_path, "900100001")
    assert rec["pending_cents"] == 0
    assert rec["paid_cents"] == 5000


def test_run_payouts_skips_below_minimum(tmp_path):
    _make_marketer(tmp_path, "900100001", 1000)  # below default 2500 min
    po._save_accounts(tmp_path, {"900100001": "acct_1"})
    opener = _opener_for([("/accounts/acct_1", {"payouts_enabled": True})])
    result = po.run_payouts(tmp_path, opener, "sk_test")
    assert result["paid"] == []
    assert result["skipped"][0]["reason"] == "below minimum"
    assert rf.ensure_profile(tmp_path, "900100001")["pending_cents"] == 1000


def test_run_payouts_skips_marketer_with_no_connect_account(tmp_path):
    _make_marketer(tmp_path, "900100001", 5000)
    opener = _opener_for([])
    result = po.run_payouts(tmp_path, opener, "sk_test")
    assert result["paid"] == []
    assert result["skipped"][0]["reason"] == "no Connect account"


def test_run_payouts_skips_incomplete_onboarding(tmp_path):
    _make_marketer(tmp_path, "900100001", 5000)
    po._save_accounts(tmp_path, {"900100001": "acct_1"})
    opener = _opener_for([("/accounts/acct_1", {"payouts_enabled": False})])
    result = po.run_payouts(tmp_path, opener, "sk_test")
    assert result["paid"] == []
    assert result["skipped"][0]["reason"] == "Connect onboarding incomplete"
    assert rf.ensure_profile(tmp_path, "900100001")["pending_cents"] == 5000


def test_run_payouts_ignores_non_marketers(tmp_path):
    rf.ensure_profile(tmp_path, "900100001")  # plain member, never a marketer
    rf.record_earning(tmp_path, "900100001", 5000, "stripe")  # shouldn't happen, but be safe
    opener = _opener_for([])
    result = po.run_payouts(tmp_path, opener, "sk_test")
    assert result["paid"] == []


def test_run_payouts_with_no_key(tmp_path):
    result = po.run_payouts(tmp_path, lambda *a: None, "")
    assert result["paid"] == []
    assert "configured" in result["detail"].lower()


def test_run_payouts_uses_a_stable_idempotency_key_per_day(tmp_path):
    _make_marketer(tmp_path, "900100001", 5000)
    po._save_accounts(tmp_path, {"900100001": "acct_1"})
    opener = _opener_for([
        ("/accounts/acct_1", {"payouts_enabled": True}),
        ("/transfers", {"id": "tr_1"}),
    ])
    po.run_payouts(tmp_path, opener, "sk_test")
    transfer_call = next(c for c in opener.calls if "/transfers" in c["url"])
    assert transfer_call["headers"]["Idempotency-Key"].startswith("payout:900100001:5000:")


def test_run_payouts_never_double_pays_two_marketers_independently(tmp_path):
    _make_marketer(tmp_path, "900100001", 5000)
    _make_marketer(tmp_path, "900200002", 3000)
    po._save_accounts(tmp_path, {"900100001": "acct_1", "900200002": "acct_2"})

    def opener(url, headers, body, timeout):
        if "/accounts/" in url:
            return _Resp({"payouts_enabled": True})
        if "/transfers" in url:
            dest = body.get("destination")
            return _Resp({"id": f"tr_{dest}"})
        return _Resp({})

    result = po.run_payouts(tmp_path, opener, "sk_test")
    assert result["total_cents"] == 8000
    assert len(result["paid"]) == 2
    assert rf.ensure_profile(tmp_path, "900100001")["paid_cents"] == 5000
    assert rf.ensure_profile(tmp_path, "900200002")["paid_cents"] == 3000
