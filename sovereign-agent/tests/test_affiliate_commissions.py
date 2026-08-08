"""Tests for affiliate_commissions.py — the attribution bridge.

Kevin, 2026-07-25: the referral system's marketer commission fields
(`earned_cents`, `pending_cents`, `MARKETER_PCT`/`MARKETER_MONTHS`) and
`record_earning()` already existed but nothing ever called it. This
module is the missing bridge — verified here against every real
condition: referred/not-referred, marketer/non-marketer, inside/outside
the 6-month window, and idempotency (record_earning itself has zero
dedup, so this module must be the only gate).
"""
from __future__ import annotations

import time

from sovereign_agent import referrals as rf
from sovereign_agent.affiliate_commissions import attribute_commission, is_attributed


def _refer(tmp_path, referrer_id, buyer_id, *, now=None):
    """Mint the referrer's real profile+code (registers the code index),
    then redeem it for the buyer — the exact setup shape test_referrals.py
    itself uses. `rf.ref_code_for(id)` alone is just a string computation;
    it never registers the code, so redeem() would see 'unknown-code'
    without this."""
    ref = rf.ensure_profile(tmp_path, referrer_id, now=now or time.time())
    return rf.redeem(tmp_path, buyer_id, ref["code"], now=now)


def test_no_commission_when_buyer_was_never_referred(tmp_path):
    rf.ensure_profile(tmp_path, "900200002")
    result = attribute_commission(tmp_path, "900200002", 2500, "ch_1")
    assert result is None


def test_no_commission_when_referrer_is_not_a_marketer(tmp_path):
    now = time.time()
    _refer(tmp_path, "900100001", "900200002", now=now)
    # referrer1 is a plain member — never opted into ROLE_MARKETER
    result = attribute_commission(tmp_path, "900200002", 2500, "ch_1", now=now)
    assert result is None
    assert rf.ensure_profile(tmp_path, "900100001")["pending_cents"] == 0


def test_commission_credited_for_a_real_marketer_referral(tmp_path):
    now = time.time()
    _refer(tmp_path, "900100001", "900200002", now=now)
    rf.set_marketer(tmp_path, "900100001", on=True)

    result = attribute_commission(tmp_path, "900200002", 2500, "ch_1", now=now)
    assert result is not None
    expected_cents = int(2500 * rf.MARKETER_PCT)
    assert result["pending_cents"] == expected_cents
    assert result["earned_cents"] == expected_cents
    assert is_attributed("ch_1", tmp_path)


def test_no_commission_outside_the_six_month_window(tmp_path):
    long_ago = time.time() - (rf.MARKETER_MONTHS * 30 * 86400) - 3600
    _refer(tmp_path, "900100001", "900200002", now=long_ago)
    rf.set_marketer(tmp_path, "900100001", on=True)

    result = attribute_commission(tmp_path, "900200002", 2500, "ch_1")
    assert result is None


def test_commission_still_credited_just_inside_the_window(tmp_path):
    almost_expired = time.time() - (rf.MARKETER_MONTHS * 30 * 86400) + 3600
    _refer(tmp_path, "900100001", "900200002", now=almost_expired)
    rf.set_marketer(tmp_path, "900100001", on=True)

    result = attribute_commission(tmp_path, "900200002", 2500, "ch_1")
    assert result is not None


def test_idempotent_by_charge_id_even_across_reruns(tmp_path):
    now = time.time()
    _refer(tmp_path, "900100001", "900200002", now=now)
    rf.set_marketer(tmp_path, "900100001", on=True)

    first = attribute_commission(tmp_path, "900200002", 2500, "ch_dup", now=now)
    second = attribute_commission(tmp_path, "900200002", 2500, "ch_dup", now=now)
    assert first is not None
    assert second is None  # already attributed — never double-credited
    assert rf.ensure_profile(tmp_path, "900100001")["pending_cents"] == int(2500 * rf.MARKETER_PCT)


def test_a_different_charge_id_is_a_genuinely_new_commission(tmp_path):
    now = time.time()
    _refer(tmp_path, "900100001", "900200002", now=now)
    rf.set_marketer(tmp_path, "900100001", on=True)

    attribute_commission(tmp_path, "900200002", 2500, "ch_1", now=now)
    attribute_commission(tmp_path, "900200002", 1000, "ch_2", now=now)
    expected = int(2500 * rf.MARKETER_PCT) + int(1000 * rf.MARKETER_PCT)
    assert rf.ensure_profile(tmp_path, "900100001")["pending_cents"] == expected


def test_rejects_empty_charge_id_and_non_positive_amount(tmp_path):
    now = time.time()
    _refer(tmp_path, "900100001", "900200002", now=now)
    rf.set_marketer(tmp_path, "900100001", on=True)

    assert attribute_commission(tmp_path, "900200002", 2500, "", now=now) is None
    assert attribute_commission(tmp_path, "900200002", 0, "ch_1", now=now) is None
    assert attribute_commission(tmp_path, "900200002", -100, "ch_1", now=now) is None


def test_no_commission_when_referred_at_is_missing_pre_existing_field(tmp_path):
    """Profiles created before referred_at existed must never be treated
    as "referred forever" — missing timestamp means no attribution, not
    an open-ended one."""
    rf.ensure_profile(tmp_path, "900200002")
    rf.ensure_profile(tmp_path, "900100001")
    rf.set_marketer(tmp_path, "900100001", on=True)
    # simulate a pre-existing profile: referred_by set, referred_at absent
    rec = rf._load(tmp_path, "900200002")
    rec["referred_by"] = "900100001"
    rec.pop("referred_at", None)
    rf._write(tmp_path, rec)

    result = attribute_commission(tmp_path, "900200002", 2500, "ch_1")
    assert result is None


def test_is_attributed_false_before_and_true_after(tmp_path):
    now = time.time()
    _refer(tmp_path, "900100001", "900200002", now=now)
    rf.set_marketer(tmp_path, "900100001", on=True)

    assert not is_attributed("ch_1", tmp_path)
    attribute_commission(tmp_path, "900200002", 2500, "ch_1", now=now)
    assert is_attributed("ch_1", tmp_path)
