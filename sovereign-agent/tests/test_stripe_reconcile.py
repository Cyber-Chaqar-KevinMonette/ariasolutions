"""Tests for stripe_reconcile — the automatic redeem, conservative by
construction. Also covers stripe_sync's new whole-book reads + buy links.
No network anywhere — injected openers only.
"""
from __future__ import annotations

import io
import json

from sovereign_agent.stripe_reconcile import (
    apply_plan,
    compose_reconcile_report,
    plan_actions,
)
from sovereign_agent.stripe_sync import buy_url, checkout_refs, list_subscriptions

NOW = 1_800_000_000.0


def _sub(sub_id="sub_1", customer="cus_1", email="kev@x.com",
         status="active", amount=1200, end=NOW + 20 * 86400):
    return {"sub_id": sub_id, "customer": customer, "email": email,
            "status": status, "plan": {500: "basic", 1200: "pro",
                                       2500: "vip"}.get(amount, "basic"),
            "amount": amount, "expires_ts": end}


# ── planning: the conservative diff ─────────────────────────────────────────
def test_buy_link_ref_maps_purchase_to_person():
    """A checkout that carried client_reference_id syncs with zero typing."""
    subs = [_sub()]
    actions = plan_actions(subs, {"sub_1": "424242"}, [], now=NOW)
    assert len(actions["syncs"]) == 1
    a = actions["syncs"][0]
    assert a["user_id"] == "424242" and a["plan"] == "pro"
    assert not actions["revokes"] and not actions["unmatched"]


def test_stored_customer_link_matches_without_ref():
    ents = [{"id": "9000", "customer": "cus_1", "source": "stripe",
             "expires_ts": 0.0}]
    actions = plan_actions([_sub()], {}, ents, now=NOW)
    assert actions["syncs"][0]["user_id"] == "9000"


def test_unmatched_sub_is_reported_never_guessed():
    actions = plan_actions([_sub()], {}, [], now=NOW)
    assert not actions["syncs"] and not actions["revokes"]
    assert len(actions["unmatched"]) == 1
    assert "kev@x.com" in actions["unmatched"][0]


def test_sync_only_when_stripe_extends():
    """Idempotence: a timer already at (or past) Stripe truth → no action."""
    ents = [{"id": "9000", "customer": "cus_1", "source": "stripe",
             "expires_ts": NOW + 20 * 86400}]
    actions = plan_actions([_sub()], {}, ents, now=NOW)
    assert actions["syncs"] == []


def test_revoke_needs_positive_evidence():
    """Only a LINKED member whose customer has no live sub gets revoked;
    manual grants and unlinked members are never touched."""
    ents = [
        {"id": "1", "customer": "cus_dead", "source": "stripe",
         "expires_ts": NOW + 5 * 86400},          # linked, sub gone → revoke
        {"id": "2", "customer": "", "source": "manual",
         "expires_ts": NOW + 5 * 86400},          # manual → never touched
        {"id": "3", "customer": "cus_1", "source": "stripe",
         "expires_ts": NOW + 5 * 86400},          # linked, sub alive → safe
    ]
    actions = plan_actions([_sub()], {}, ents, now=NOW)
    assert [r["user_id"] for r in actions["revokes"]] == ["1"]


def test_empty_read_never_revokes_anyone():
    """The exact fear: a network blip must not strip access."""
    ents = [{"id": "1", "customer": "cus_dead", "source": "stripe",
             "expires_ts": NOW + 5 * 86400}]
    actions = plan_actions([], {}, ents, now=NOW)
    assert actions == {"syncs": [], "revokes": [], "unmatched": []}


def test_past_due_keeps_access_dunning_grace():
    ents = [{"id": "1", "customer": "cus_1", "source": "stripe",
             "expires_ts": NOW + 1 * 86400}]
    actions = plan_actions([_sub(status="past_due")], {}, ents, now=NOW)
    assert not actions["revokes"]                 # grace, not a cutoff
    assert actions["syncs"]                       # timer still follows truth


# ── applying: monotone writes + honest receipts ─────────────────────────────
def test_apply_plan_writes_timers_and_links(tmp_path):
    from sovereign_agent import entitlements
    actions = plan_actions([_sub()], {"sub_1": "424242"}, [], now=NOW)
    receipts = apply_plan(tmp_path, actions, now=NOW)
    assert len(receipts["synced"]) == 1
    st = entitlements.status(tmp_path, "424242", now=NOW)
    assert st["active"] and st["plan"] == "pro" and st["source"] == "stripe"
    rec = entitlements.load(tmp_path, "424242")
    assert rec["customer"] == "cus_1"             # linked for next time
    # re-running the same plan is a no-op on the timer (monotone)
    before = rec["expires_ts"]
    apply_plan(tmp_path, actions, now=NOW)
    assert entitlements.load(tmp_path, "424242")["expires_ts"] == before


def test_report_is_honest_and_calm():
    quiet = compose_reconcile_report({"syncs": [], "revokes": [],
                                      "unmatched": []})
    assert "already matches" in quiet
    busy = compose_reconcile_report(plan_actions(
        [_sub()], {"sub_1": "424242"}, [], now=NOW))
    assert "<@424242>" in busy and "PRO" in busy


# ── stripe_sync: the whole-book reads (injected opener) ─────────────────────
class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def test_list_subscriptions_parses_expanded_customers():
    payload = {"data": [{
        "id": "sub_9", "status": "active",
        "customer": {"id": "cus_9", "email": "Kev@X.com"},
        "current_period_end": NOW + 86400,
        "items": {"data": [{"price": {"unit_amount": 2500,
                                      "product": "prod_1"}}]}}]}
    subs = list_subscriptions(lambda u, h, t: _Resp(payload), "sk_test")
    assert subs == [{"sub_id": "sub_9", "customer": "cus_9",
                     "email": "kev@x.com", "status": "active",
                     "plan": "vip", "amount": 2500,
                     "expires_ts": NOW + 86400}]


def test_checkout_refs_maps_sub_to_discord_id():
    payload = {"data": [
        {"client_reference_id": "424242", "subscription": "sub_9"},
        {"client_reference_id": None, "subscription": "sub_8"},
        {"client_reference_id": "777", "subscription": None},
    ]}
    refs = checkout_refs(lambda u, h, t: _Resp(payload), "sk_test")
    assert refs == {"sub_9": "424242"}


def test_reads_fail_safe_to_empty():
    def boom(u, h, t):
        raise OSError("down")
    assert list_subscriptions(boom, "sk") == []
    assert checkout_refs(boom, "sk") == {}


def test_buy_url_carries_the_discord_id():
    assert buy_url("https://buy.stripe.com/x", "424242") == \
        "https://buy.stripe.com/x?client_reference_id=424242"
    assert buy_url("https://buy.stripe.com/x?a=1", "42") == \
        "https://buy.stripe.com/x?a=1&client_reference_id=42"
    assert buy_url("", "42") == ""                # degrade, never crash
    assert buy_url("https://x", "") == "https://x"
