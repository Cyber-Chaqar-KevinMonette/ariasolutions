"""Tests for stripe_sync — purchase confirmation with an injected opener."""
from __future__ import annotations

import io
import json

from sovereign_agent import stripe_sync as ss


class _Resp:
    def __init__(self, payload): self._b = json.dumps(payload).encode()
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _opener_for(routes):
    """routes: list of (substring, payload) matched against the URL in order."""
    def opener(url, headers, timeout):
        assert headers["Authorization"].startswith("Bearer ")
        for frag, payload in routes:
            if frag in url:
                return _Resp(payload)
        return _Resp({"data": []})
    return opener


def test_confirm_active_vip():
    opener = _opener_for([
        ("/customers", {"data": [{"id": "cus_1"}]}),
        ("/subscriptions", {"data": [{
            "status": "active", "current_period_end": 1790000000,
            "items": {"data": [{"price": {"unit_amount": 2500,
                                          "product": "prod_vip"}}]}}]}),
    ])
    out = ss.confirm_purchase(opener, "sk_test_x", "buyer@example.com")
    assert out["found"] and out["active"]
    assert out["plan"] == "vip" and out["expires_ts"] == 1790000000
    assert out["customer"] == "cus_1"


def test_confirm_no_customer():
    opener = _opener_for([("/customers", {"data": []})])
    out = ss.confirm_purchase(opener, "sk_test_x", "nobody@example.com")
    assert not out["found"] and not out["active"]
    assert "no stripe customer" in out["detail"].lower()


def test_confirm_customer_but_no_active_sub():
    opener = _opener_for([
        ("/customers", {"data": [{"id": "cus_2"}]}),
        ("/subscriptions", {"data": [{"status": "canceled",
                                      "items": {"data": []}}]}),
    ])
    out = ss.confirm_purchase(opener, "sk_test_x", "lapsed@example.com")
    assert out["found"] and not out["active"]
    assert "no active subscription" in out["detail"].lower()


def test_unknown_amount_falls_back_to_basic():
    opener = _opener_for([
        ("/customers", {"data": [{"id": "cus_3"}]}),
        ("/subscriptions", {"data": [{
            "status": "active", "current_period_end": 1790000000,
            "items": {"data": [{"price": {"unit_amount": 999}}]}}]}),
    ])
    out = ss.confirm_purchase(opener, "sk_test_x", "odd@example.com")
    assert out["active"] and out["plan"] == "basic"


def test_bad_email_and_missing_key():
    opener = _opener_for([])
    assert not ss.confirm_purchase(opener, "sk", "notanemail")["found"]
    assert "email" in ss.confirm_purchase(opener, "sk", "notanemail")["detail"]
    assert not ss.confirm_purchase(opener, "", "a@b.com")["found"]


def test_401_is_reported_honestly():
    def opener(url, headers, timeout):
        raise type("E", (Exception,), {"code": 401})()
    out = ss.confirm_purchase(opener, "sk_bad", "x@y.com")
    assert not out["found"] and "roll it" in out["detail"].lower()


# ── income-ledger-d — sync_verified_income ──────────────────────────────────
def test_sync_verified_income_ledgers_succeeded_charges(tmp_path):
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_1", "status": "succeeded", "paid": True,
             "refunded": False, "amount": 2500, "description": "VIP"},
            {"id": "ch_2", "status": "succeeded", "paid": True,
             "refunded": False, "amount": 500, "description": "Basic"},
        ]}),
    ])
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert result["synced"] == 2
    assert result["total_cents"] == 3000
    assert result["detail"] == "ok"


def test_sync_verified_income_skips_pending_failed_and_refunded(tmp_path):
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_pending", "status": "pending", "paid": False, "amount": 500},
            {"id": "ch_failed", "status": "failed", "paid": False, "amount": 500},
            {"id": "ch_unpaid", "status": "succeeded", "paid": False, "amount": 500},
            {"id": "ch_refunded", "status": "succeeded", "paid": True,
             "refunded": True, "amount": 500},
            {"id": "ch_real", "status": "succeeded", "paid": True,
             "refunded": False, "amount": 1200},
        ]}),
    ])
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert result["synced"] == 1
    assert result["total_cents"] == 1200


def test_sync_verified_income_is_idempotent_across_calls(tmp_path):
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_dup", "status": "succeeded", "paid": True,
             "refunded": False, "amount": 2500},
        ]}),
    ])
    first = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    second = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert first["synced"] == 1
    assert second["synced"] == 0  # already ledgered — never double-counted
    assert second["total_cents"] == 2500


def test_sync_verified_income_with_no_key(tmp_path):
    result = ss.sync_verified_income(lambda *a: None, "", data_dir=tmp_path)
    assert result["synced"] == 0
    assert "configured" in result["detail"].lower()


def test_sync_verified_income_401_is_reported_honestly(tmp_path):
    def opener(url, headers, timeout):
        raise type("E", (Exception,), {"code": 401})()
    result = ss.sync_verified_income(opener, "sk_bad", data_dir=tmp_path)
    assert result["synced"] == 0
    assert "roll it" in result["detail"].lower()


# ── affiliate-commissions-d — sync_verified_income attributes commissions ──
def _mint_marketer_referral(tmp_path, referrer_id, buyer_id):
    from sovereign_agent import referrals as rf
    ref = rf.ensure_profile(tmp_path, referrer_id)
    rf.redeem(tmp_path, buyer_id, ref["code"])
    rf.set_marketer(tmp_path, referrer_id, on=True)


def test_checkout_refs_by_payment_intent():
    opener = _opener_for([
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900200002", "payment_intent": "pi_1"},
            {"client_reference_id": "", "payment_intent": "pi_2"},  # no ref — skipped
        ]}),
    ])
    out = ss.checkout_refs_by_payment_intent(opener, "sk_test_x")
    assert out == {"pi_1": "900200002"}


def test_sync_verified_income_attributes_via_payment_intent(tmp_path):
    """A one-time purchase (no subscription/invoice) — resolved via the
    checkout session's payment_intent, the only link a one-time charge
    carries."""
    _mint_marketer_referral(tmp_path, "900100001", "900200002")
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_1", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 2500, "payment_intent": "pi_1"},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900200002", "payment_intent": "pi_1"},
        ]}),
    ])
    ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)

    from sovereign_agent import referrals as rf
    rec = rf.ensure_profile(tmp_path, "900100001")
    assert rec["pending_cents"] == int(2500 * rf.MARKETER_PCT)


def test_sync_verified_income_attributes_via_subscription(tmp_path):
    """A recurring subscription charge — the charge's expanded
    invoice.subscription resolves the buyer, since a renewal's own
    payment_intent never matches the original checkout session."""
    _mint_marketer_referral(tmp_path, "900100001", "900200002")
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_1", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 1200, "payment_intent": "pi_renewal_999",
             "invoice": {"subscription": "sub_1"}},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900200002", "subscription": "sub_1",
             "payment_intent": "pi_original_111"},
        ]}),
    ])
    ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)

    from sovereign_agent import referrals as rf
    rec = rf.ensure_profile(tmp_path, "900100001")
    assert rec["pending_cents"] == int(1200 * rf.MARKETER_PCT)


def test_sync_verified_income_attributes_nothing_for_an_unreferred_buyer(tmp_path):
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_1", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 2500, "payment_intent": "pi_1"},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900299999", "payment_intent": "pi_1"},
        ]}),
    ])
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert result["synced"] == 1  # income sync itself is untouched

    from sovereign_agent.affiliate_commissions import is_attributed
    assert not is_attributed("ch_1", tmp_path)


def test_sync_verified_income_survives_checkout_sessions_failure(tmp_path):
    """Attribution is best-effort — if the checkout-session lookup fails,
    the income sync itself must still succeed."""
    def opener(url, headers, timeout):
        if "/checkout/sessions" in url:
            raise RuntimeError("boom")
        return _Resp({"data": [
            {"id": "ch_1", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 2500, "payment_intent": "pi_1"},
        ]})
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert result["synced"] == 1
    assert result["detail"] == "ok"


# ── passes-d (Kevin, 2026-07-26) — one-time pass purchases → entitlements ──

def test_pass_plans_cover_all_four_durations():
    assert ss.PASS_PLANS[300] == ("pass-24h", 1.0)
    assert ss.PASS_PLANS[900] == ("pass-week", 7.0)
    assert ss.PASS_PLANS[1900] == ("pass-month", 30.0)
    assert ss.PASS_PLANS[14900] == ("pass-year", 365.0)


def test_sync_verified_income_grants_a_pass_for_a_recognized_one_time_charge(tmp_path):
    """A 24-hour pass purchase (a one-time charge whose amount matches
    PASS_PLANS) becomes a real entitlement grant, resolved via the same
    payment_intent buyer-resolution attribution already uses."""
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_pass", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 300, "payment_intent": "pi_pass_1"},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900300003", "payment_intent": "pi_pass_1"},
        ]}),
    ])
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)

    assert result["pass_grants"] == [{"user_id": "900300003", "plan": "pass-24h",
                                      "days": 1.0}]
    from sovereign_agent import entitlements
    st = entitlements.status(tmp_path, "900300003")
    assert st["active"] and st["plan"] == "pass-24h"
    assert st["role"] == "Pass-Holder"


def test_sync_verified_income_never_grants_a_pass_twice_for_the_same_charge(tmp_path):
    """The dedup guard is record_income's own charge-id idempotency —
    re-polling the same charge must never re-grant (stack) days."""
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_pass", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 900, "payment_intent": "pi_pass_2"},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900300004", "payment_intent": "pi_pass_2"},
        ]}),
    ])
    first = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    second = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)

    assert len(first["pass_grants"]) == 1
    assert second["pass_grants"] == []          # already ledgered — no re-grant

    from sovereign_agent import entitlements
    st = entitlements.status(tmp_path, "900300004")
    assert 6.9 < st["days_left"] <= 7.0          # exactly one week's worth, not two


def test_sync_verified_income_ignores_amounts_that_arent_a_pass(tmp_path):
    """A normal (non-pass) charge amount must never accidentally grant a
    pass entitlement."""
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_normal", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 2500, "payment_intent": "pi_normal"},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900300005", "payment_intent": "pi_normal"},
        ]}),
    ])
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert result["pass_grants"] == []

    from sovereign_agent import entitlements
    assert not entitlements.is_active(tmp_path, "900300005")


def test_sync_verified_income_pass_grant_failure_never_breaks_income_sync(tmp_path, monkeypatch):
    """A pass-grant failure is best-effort, same discipline as commission
    attribution — the income sync itself must still succeed."""
    import sovereign_agent.entitlements as ent
    monkeypatch.setattr(ent, "grant",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    opener = _opener_for([
        ("/charges", {"data": [
            {"id": "ch_pass_fail", "status": "succeeded", "paid": True, "refunded": False,
             "amount": 300, "payment_intent": "pi_pass_fail"},
        ]}),
        ("/checkout/sessions", {"data": [
            {"client_reference_id": "900300006", "payment_intent": "pi_pass_fail"},
        ]}),
    ])
    result = ss.sync_verified_income(opener, "sk_test_x", data_dir=tmp_path)
    assert result["synced"] == 1
    assert result["detail"] == "ok"
    assert result["pass_grants"] == []
