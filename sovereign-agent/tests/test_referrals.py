"""Tests for referrals — codes, credits, redemption, the game ranks."""
from __future__ import annotations

import json
import time

from sovereign_agent import referrals as rf


def _fresh_snowflake(now: float) -> str:
    """A syntactically valid Discord ID whose encoded creation time is
    ~now (i.e., a brand-new account) — for exercising the sybil checks."""
    created_ms = int(now * 1000)
    return str((created_ms - rf.DISCORD_EPOCH_MS) << 22)


def test_code_is_deterministic_and_unique():
    a1 = rf.ref_code_for("123")
    a2 = rf.ref_code_for("123")
    b = rf.ref_code_for("456")
    assert a1 == a2 and a1.startswith("REF-")
    assert a1 != b


def test_ensure_profile_registers_code(tmp_path):
    rec = rf.ensure_profile(tmp_path, "111")
    assert rec["code"] == rf.ref_code_for("111")
    assert rf.resolve_code(tmp_path, rec["code"]) == "111"
    # resolve tolerates a bare (no REF-) code
    assert rf.resolve_code(tmp_path, rec["code"].replace("REF-", "")) == "111"


def test_redeem_rewards_both_sides_once(tmp_path):
    ref = rf.ensure_profile(tmp_path, "111")           # referrer
    out = rf.redeem(tmp_path, "222", ref["code"])
    assert out["ok"] and out["referrer_id"] == "111"
    assert rf.credits_of(tmp_path, "111") == rf.CREDIT_PER_REFERRAL
    assert rf.credits_of(tmp_path, "222") == rf.CREDIT_PER_REFERRAL
    # a second redeem by the same newbie does nothing (no double reward)
    out2 = rf.redeem(tmp_path, "222", ref["code"])
    assert not out2["ok"] and out2["reason"] == "already-referred"
    assert rf.credits_of(tmp_path, "111") == rf.CREDIT_PER_REFERRAL


def test_no_self_referral_and_unknown_code(tmp_path):
    me = rf.ensure_profile(tmp_path, "111")
    assert rf.redeem(tmp_path, "111", me["code"])["reason"] == "self-referral"
    assert rf.redeem(tmp_path, "333", "REF-NOPE")["reason"] == "unknown-code"


def test_credits_spend_never_negative(tmp_path):
    rf.grant_credits(tmp_path, "111", 2, "test")
    assert rf.try_spend_credit(tmp_path, "111") is True
    assert rf.credits_of(tmp_path, "111") == 1
    assert rf.try_spend_credit(tmp_path, "111") is True
    assert rf.try_spend_credit(tmp_path, "111") is False   # empty → no spend
    assert rf.credits_of(tmp_path, "111") == 0


def test_rank_ladder_climbs():
    rank = rf.rank_for(0)
    assert "Newcomer" in rank["title"] and rank["next_at"] == 1
    assert "Ambassador" in rf.rank_for(5)["title"]
    top = rf.rank_for(999)
    assert top["next_title"] is None and top["to_next"] == 0


def test_earning_records_pending_but_pays_nothing(tmp_path):
    rf.set_marketer(tmp_path, "111", True)
    rf.record_earning(tmp_path, "111", 500, "sub_test")
    from sovereign_agent.referrals import _load
    rec = _load(tmp_path, "111")
    assert rec["earned_cents"] == 500 and rec["pending_cents"] == 500
    assert rec["paid_cents"] == 0                       # nothing paid here
    txt = rf.compose_earnings(tmp_path, "111")
    assert "$5.00" in txt and "Pending" in txt


def test_leaderboard_and_refer_render(tmp_path):
    ref = rf.ensure_profile(tmp_path, "111")
    rf.redeem(tmp_path, "222", ref["code"])
    lb = rf.compose_leaderboard(tmp_path)
    assert "Champions" in lb and "1" in lb
    card = rf.compose_refer(tmp_path, "111")
    assert ref["code"] in card and "credits" in card.lower()


# ── H1a: sybil resistance ────────────────────────────────────────────────────

def test_account_age_days_decodes_snowflake():
    now = time.time()
    # a tiny numeric ID has (id >> 22) == 0 -> decodes to the Discord
    # epoch itself (2015-01-01) -> ancient, comfortably passes any policy
    assert rf.account_age_days("111", now=now) > 3650
    # a freshly-minted snowflake for `now` decodes to ~0 days old
    fresh = _fresh_snowflake(now)
    assert rf.account_age_days(fresh, now=now) < 0.01
    # malformed input never raises — treated as brand-new (conservative)
    assert rf.account_age_days("not-an-id") == 0.0
    assert rf.account_age_days("") == 0.0


def test_redeem_holds_when_newbie_account_too_new(tmp_path):
    now = time.time()
    ref = rf.ensure_profile(tmp_path, "111", now=now)
    fresh = _fresh_snowflake(now)
    out = rf.redeem(tmp_path, fresh, ref["code"], now=now)
    assert not out["ok"] and out["reason"] == "held-for-review"
    assert out["referrer_id"] == "111"
    # no credits moved on EITHER side — held means held, not partially applied
    assert rf.credits_of(tmp_path, "111") == 0
    assert rf.credits_of(tmp_path, fresh) == 0
    # never silently dropped — a distinct ledger event + diagnosis case exist
    ledger_lines = (rf._ledger_path(tmp_path)).read_text().splitlines()
    kinds = [json.loads(l)["kind"] for l in ledger_lines]
    assert "referral-held" in kinds
    from sovereign_agent.diagnosis import ConflictCatalog
    cases = ConflictCatalog(tmp_path / "diagnoses").all_cases()
    assert any(c.type == "ambiguity" for c in cases)


def test_redeem_holds_when_referrer_exceeds_velocity_cap(tmp_path):
    now = time.time()
    policy = rf.SybilPolicy(min_account_age_days=0.0,
                            max_referrals_per_window=2, window_hours=24.0)
    ref = rf.ensure_profile(tmp_path, "111", now=now)
    # two legitimate (old-enough) referrals fill the cap
    for uid in ("222", "333"):
        out = rf.redeem(tmp_path, uid, ref["code"], now=now,
                        sybil_policy=policy)
        assert out["ok"], out
    # the third, otherwise-legitimate referral is held on velocity alone
    out3 = rf.redeem(tmp_path, "444", ref["code"], now=now, sybil_policy=policy)
    assert not out3["ok"] and out3["reason"] == "held-for-review"
    assert rf.credits_of(tmp_path, "444") == 0


def test_default_policy_allows_a_normal_referral(tmp_path):
    """The hardening must never break the ordinary path (old test-style
    small IDs, one redemption) — regression guard for the defaults."""
    ref = rf.ensure_profile(tmp_path, "111")
    out = rf.redeem(tmp_path, "222", ref["code"])
    assert out["ok"]
    assert rf.credits_of(tmp_path, "111") == rf.CREDIT_PER_REFERRAL


# ── H1b: ledger reconciliation ──────────────────────────────────────────────

def test_ledger_consistency_clean_after_normal_activity(tmp_path):
    ref = rf.ensure_profile(tmp_path, "111")
    rf.redeem(tmp_path, "222", ref["code"])
    rf.try_spend_credit(tmp_path, "222")
    report = rf.verify_ledger_consistency(tmp_path)
    assert report["consistent"] is True
    assert report["drift"] == []


def test_ledger_consistency_detects_injected_drift(tmp_path):
    ref = rf.ensure_profile(tmp_path, "111")
    rf.redeem(tmp_path, "222", ref["code"])
    # corrupt the profile directly, bypassing the ledger (simulating a
    # bug or a hand-edit) — the reconciler must catch it
    rec = rf._load(tmp_path, "111")
    rec["credits"] = 99999
    rf._write(tmp_path, rec)
    report = rf.verify_ledger_consistency(tmp_path)
    assert report["consistent"] is False
    hit = [d for d in report["drift"] if d["user"] == "111"]
    assert hit and hit[0]["field"] == "credits"
    assert hit[0]["profile_value"] == 99999
    assert hit[0]["ledger_sum"] == rf.CREDIT_PER_REFERRAL


def test_ledger_consistency_survives_clamped_history(tmp_path):
    """The reconciler must replay the SAME clamp transition grant_credits
    uses live, not just sum raw deltas — otherwise a ceiling-clamped
    history would falsely report as drifted."""
    rf.grant_credits(tmp_path, "111", rf.MAX_CREDITS + 500, "big grant")
    assert rf.credits_of(tmp_path, "111") == rf.MAX_CREDITS
    report = rf.verify_ledger_consistency(tmp_path)
    assert report["consistent"] is True


# ── H1c: write-failure visibility ───────────────────────────────────────────

def test_write_failure_opens_a_diagnosis_case_not_silent(tmp_path):
    # put a FILE where the referrals directory needs to be created ->
    # mkdir(parents=True) inside _write raises, exercising the failure path
    blocker = tmp_path / "community"
    blocker.write_text("i am a file, not a directory")
    rf.ensure_profile(tmp_path, "111")   # triggers _write -> fails -> reported
    from sovereign_agent.diagnosis import ConflictCatalog
    cases = ConflictCatalog(tmp_path / "diagnoses").all_cases()
    assert any(c.type == "omission" and "_write" in c.trigger_event
              for c in cases)


# ── H1d: idempotency + credit ceiling ───────────────────────────────────────

def test_grant_credits_idempotency_key_blocks_replay(tmp_path):
    rf.grant_credits(tmp_path, "111", 10, "bonus", idempotency_key="evt-1")
    rf.grant_credits(tmp_path, "111", 10, "bonus", idempotency_key="evt-1")
    assert rf.credits_of(tmp_path, "111") == 10          # applied ONCE
    rf.grant_credits(tmp_path, "111", 10, "bonus", idempotency_key="evt-2")
    assert rf.credits_of(tmp_path, "111") == 20           # a NEW key applies


def test_grant_credits_clamps_to_ceiling(tmp_path):
    rf.grant_credits(tmp_path, "111", rf.MAX_CREDITS + 1000, "huge")
    assert rf.credits_of(tmp_path, "111") == rf.MAX_CREDITS
    rf.grant_credits(tmp_path, "111", 500, "more")
    assert rf.credits_of(tmp_path, "111") == rf.MAX_CREDITS   # still clamped
    rf.try_spend_credit(tmp_path, "111", 10)
    assert rf.credits_of(tmp_path, "111") == rf.MAX_CREDITS - 10  # spend works


# ── affiliate-section-d — publish_affiliate_section ─────────────────────────
def test_publish_affiliate_section_sends_pitch_then_leaderboard(tmp_path, monkeypatch):
    """Kevin, 2026-07-25: "add an affiliates section in the discord" —
    same webhook-publish pattern as shop.publish_storefront."""
    sends = []

    class FakeDelivery:
        def __init__(self, env, live=False):
            pass

        def send(self, text, embeds=None, username=""):
            sends.append(text)
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=True, dry_run=False, detail="ok")

    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", FakeDelivery)

    rf.publish_affiliate_section(tmp_path, live=True)
    assert len(sends) == 2
    assert "Referral Program" in sends[0]
    assert "/refer" in sends[0]
    assert "Community Champions" in sends[1]  # the leaderboard


def test_mark_paid_moves_pending_to_paid(tmp_path):
    rf.record_earning(tmp_path, "111", 1000, "stripe")
    rec = rf.mark_paid(tmp_path, "111", 1000, transfer_id="tr_1")
    assert rec["pending_cents"] == 0
    assert rec["paid_cents"] == 1000


def test_mark_paid_is_idempotent_by_transfer_id(tmp_path):
    rf.record_earning(tmp_path, "111", 1000, "stripe")
    rf.mark_paid(tmp_path, "111", 1000, transfer_id="tr_dup")
    rf.mark_paid(tmp_path, "111", 1000, transfer_id="tr_dup")
    rec = rf.ensure_profile(tmp_path, "111")
    assert rec["paid_cents"] == 1000          # not double-moved
    assert rec["pending_cents"] == 0


def test_mark_paid_never_takes_pending_negative(tmp_path):
    rf.record_earning(tmp_path, "111", 500, "stripe")
    rec = rf.mark_paid(tmp_path, "111", 1000, transfer_id="tr_1")  # more than pending
    assert rec["pending_cents"] == 0          # clamped, never negative
    assert rec["paid_cents"] == 1000


def test_publish_affiliate_section_stops_if_pitch_fails_to_send(tmp_path, monkeypatch):
    class FakeFailingDelivery:
        def __init__(self, env, live=False):
            pass

        def send(self, text, embeds=None, username=""):
            from sovereign_agent.discord_runtime.delivery import DeliveryResult
            return DeliveryResult(sent=False, dry_run=False, detail="no webhook")

    import sovereign_agent.discord_runtime.delivery as dmod
    monkeypatch.setattr(dmod, "WebhookDelivery", FakeFailingDelivery)

    result = rf.publish_affiliate_section(tmp_path, live=True)
    assert not result.sent
