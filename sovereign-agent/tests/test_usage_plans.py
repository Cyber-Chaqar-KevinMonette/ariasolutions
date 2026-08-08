"""Tests for usage_plans (the normal-AI-company quota shape) and
redemption_queue (the wait-your-turn gate)."""
from __future__ import annotations

import json

from sovereign_agent.usage_plans import (
    FREE_QUOTA,
    PLAN_QUOTAS,
    compose_usage,
    quota_for,
    try_consume,
    usage_state,
    used_today,
)

NOON = 1_800_000_000.0            # some fixed instant


def test_free_tier_quota_and_the_wall(tmp_path):
    uid = "100"
    for _ in range(FREE_QUOTA):
        assert try_consume(tmp_path, uid, now=NOON)
    assert not try_consume(tmp_path, uid, now=NOON)      # the wall
    assert used_today(tmp_path, uid, now=NOON) == FREE_QUOTA  # not overcounted


def test_daily_reset_at_midnight(tmp_path):
    uid = "100"
    for _ in range(FREE_QUOTA):
        try_consume(tmp_path, uid, now=NOON)
    tomorrow = NOON + 86400
    assert try_consume(tmp_path, uid, now=tomorrow)      # fresh quota
    assert used_today(tmp_path, uid, now=tomorrow) == 1


def test_plan_lifts_the_quota(tmp_path):
    from sovereign_agent.entitlements import grant
    grant(tmp_path, "200", "pro", 30, now=NOON)
    assert quota_for(tmp_path, "200", now=NOON) == PLAN_QUOTAS["pro"]
    # lapsed plan falls back to free
    grant(tmp_path, "300", "vip", 30, now=NOON - 40 * 86400)
    assert quota_for(tmp_path, "300", now=NOON) == FREE_QUOTA


def test_pass_plans_get_vip_equivalent_quota(tmp_path):
    """passes-d (Kevin, 2026-07-26): all-access passes match VIP's quota
    regardless of duration."""
    from sovereign_agent.entitlements import grant
    for plan in ("pass-24h", "pass-week", "pass-month", "pass-year"):
        uid = f"u-{plan}"
        grant(tmp_path, uid, plan, 30, now=NOON)
        assert quota_for(tmp_path, uid, now=NOON) == PLAN_QUOTAS["vip"]


def test_owner_pass_is_effectively_unlimited(tmp_path):
    """The fix for a real gap: Kevin himself had no quota bypass unless
    he held an active plan. An owner-pass entitlement closes it using the
    existing mechanism."""
    from sovereign_agent.entitlements import grant
    grant(tmp_path, "owner-id", "owner-pass", 36500, now=NOON)
    assert quota_for(tmp_path, "owner-id", now=NOON) == PLAN_QUOTAS["owner-pass"]
    assert quota_for(tmp_path, "owner-id", now=NOON) > 10000


def test_usage_state_and_meter_render(tmp_path):
    from sovereign_agent.entitlements import grant
    grant(tmp_path, "200", "basic", 30, now=NOON)
    try_consume(tmp_path, "200", now=NOON)
    s = usage_state(tmp_path, "200", now=NOON)
    assert s["plan"] == "basic" and s["quota"] == PLAN_QUOTAS["basic"]
    assert s["used"] == 1 and s["left"] == PLAN_QUOTAS["basic"] - 1
    out = compose_usage(tmp_path, "200", now=NOON)
    assert "BASIC" in out and "1/25" in out and "/refer" in out


def test_limit_banner_offers_the_upgrade_path(tmp_path):
    uid = "400"
    for _ in range(FREE_QUOTA):
        try_consume(tmp_path, uid, now=NOON)
    out = compose_usage(tmp_path, uid, now=NOON)
    assert "#storefront" in out                          # the upgrade path


def test_corrupt_counter_degrades_to_fresh(tmp_path):
    p = tmp_path / "ask_usage" / "500.json"
    p.parent.mkdir(parents=True)
    p.write_text("NOT JSON", encoding="utf-8")
    assert used_today(tmp_path, "500", now=NOON) == 0
    assert try_consume(tmp_path, "500", now=NOON)


# ── redemption queue: the wait-your-turn gate ───────────────────────────────
def _session_dir(tmp_path, sid, status, updated_iso):
    d = tmp_path / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text(json.dumps({
        "session_id": sid, "goal": "g", "mode": "auto-1h", "status": status,
        "created_at": updated_iso, "updated_at": updated_iso,
        "subtasks": []}), encoding="utf-8")


def test_mid_task_gate_fresh_active_blocks(tmp_path):
    import time as _t
    from sovereign_agent.redemption_queue import is_mid_task
    now = _t.time()
    iso = __import__("datetime").datetime.fromtimestamp(now).isoformat()
    _session_dir(tmp_path, "s1", "active", iso)
    assert is_mid_task(tmp_path, now=now) is True        # she's working
    # a stale 'active' (crash leftover) never blocks forever
    assert is_mid_task(tmp_path, now=now + 3600) is False
    # finished sessions never block
    _session_dir(tmp_path, "s1", "completed", iso)
    assert is_mid_task(tmp_path, now=now) is False


def test_mid_task_gate_fails_open(tmp_path):
    from sovereign_agent.redemption_queue import is_mid_task
    assert is_mid_task(tmp_path / "nowhere") is False    # members never stranded


def test_redemption_list_composes_time_and_bonus_questions(tmp_path):
    from sovereign_agent.redemption_queue import compose_redemption_list
    actions = {"syncs": [{"user_id": "42", "plan": "pro",
                          "expires_ts": NOON + 20 * 86400,
                          "customer": "cus_1", "why": "stripe active"}],
               "revokes": [], "unmatched": ["vip $25/mo (a@b.com) — no link"]}
    out = compose_redemption_list(actions, tmp_path, mid_task=True, now=NOON)
    assert "<@42>" in out and "PRO" in out and "+20 days" in out
    assert "bonus question" in out
    assert "holding" in out                              # the gate is visible
    quiet = compose_redemption_list({"syncs": [], "revokes": [],
                                     "unmatched": []}, tmp_path,
                                    mid_task=False, now=NOON)
    assert "empty" in quiet
