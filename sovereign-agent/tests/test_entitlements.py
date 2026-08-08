"""Tests for entitlements — the subscription timer."""
from __future__ import annotations

from sovereign_agent import entitlements as ent


def test_grant_sets_expiry_and_role(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "vip", 30, source="manual", now=now)
    st = ent.status(tmp_path, "111", now=now)
    assert st["active"] and st["plan"] == "vip"
    assert st["role"] == "Subscriber-VIP"
    assert 29.9 < st["days_left"] <= 30.0


def test_renewal_stacks_not_resets(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "basic", 30, now=now)
    # renew 10 days before expiry → time should STACK, not restart
    ent.grant(tmp_path, "111", "basic", 30, now=now + 20 * ent.DAY)
    left = ent.days_left(tmp_path, "111", now=now + 20 * ent.DAY)
    assert 39.9 < left <= 40.0            # 10 remaining + 30 new


def test_lapsed_grant_starts_fresh(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "basic", 10, now=now)
    # long after expiry, a new grant starts from now (no negative stacking)
    ent.grant(tmp_path, "111", "basic", 30, now=now + 100 * ent.DAY)
    left = ent.days_left(tmp_path, "111", now=now + 100 * ent.DAY)
    assert 29.9 < left <= 30.0


def test_expiry_and_revoke(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "vip", 5, now=now)
    assert ent.is_active(tmp_path, "111", now=now + 4 * ent.DAY)
    assert not ent.is_active(tmp_path, "111", now=now + 6 * ent.DAY)
    ent.revoke(tmp_path, "111", "chargeback", now=now + 1 * ent.DAY)
    assert not ent.is_active(tmp_path, "111", now=now + 1 * ent.DAY + 10)


def test_extend_days_bonus(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "basic", 30, now=now)
    ent.extend_days(tmp_path, "111", 7, reason="referral bonus", now=now)
    assert 36.9 < ent.days_left(tmp_path, "111", now=now) <= 37.0


def test_list_active_and_history(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "vip", 30, now=now)
    ent.grant(tmp_path, "222", "basic", 1, now=now)
    active = ent.list_active(tmp_path, now=now + 2 * ent.DAY)  # 222 expired
    assert [a["id"] for a in active] == ["111"]
    rec = ent.load(tmp_path, "111")
    assert rec["history"][0]["action"] == "grant"


def test_compose_status_active_and_none(tmp_path):
    now = 1_000_000.0
    out = ent.compose_status(tmp_path, "111", now=now)
    assert "none active" in out.lower()
    ent.grant(tmp_path, "111", "vip", 30, now=now)
    out = ent.compose_status(tmp_path, "111", now=now)
    assert "VIP" in out and "left" in out


# ── passes-d (Kevin, 2026-07-26): 24h/week/month/year + special passes ────

def test_pass_plans_share_one_role():
    """One shared all-access role — the entitlement's own `plan` field
    still distinguishes which pass someone holds."""
    assert ent.PLAN_ROLES["pass-24h"] == "Pass-Holder"
    assert ent.PLAN_ROLES["pass-week"] == "Pass-Holder"
    assert ent.PLAN_ROLES["pass-month"] == "Pass-Holder"
    assert ent.PLAN_ROLES["pass-year"] == "Pass-Holder"


def test_special_passes_map_to_the_right_roles():
    """staff-pass reuses the REAL Support role rather than inventing a
    parallel one; owner/admin get their own badge roles."""
    assert ent.PLAN_ROLES["owner-pass"] == "Owner-Pass"
    assert ent.PLAN_ROLES["admin-pass"] == "Admin-Pass"
    assert ent.PLAN_ROLES["staff-pass"] == "Support"


def test_granting_a_24h_pass_round_trips(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "pass-24h", 1, source="stripe", now=now)
    st = ent.status(tmp_path, "111", now=now)
    assert st["active"] and st["plan"] == "pass-24h"
    assert st["role"] == "Pass-Holder"
    assert 0.9 < st["days_left"] <= 1.0
    assert not ent.is_active(tmp_path, "111", now=now + 2 * ent.DAY)


def test_granting_an_owner_pass_for_a_century_stays_active_far_out(tmp_path):
    now = 1_000_000.0
    ent.grant(tmp_path, "111", "owner-pass", 36500, source="manual", now=now)
    assert ent.is_active(tmp_path, "111", now=now + 50 * 365 * ent.DAY)
    st = ent.status(tmp_path, "111", now=now)
    assert st["role"] == "Owner-Pass"
