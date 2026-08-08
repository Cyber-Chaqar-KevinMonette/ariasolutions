"""Tests for integrity_sentinel — Aria's defensive host guardian.

The load-bearing tests are the safety invariant: reversible containment is
always free; irreversible healing ('surgery') is NEVER authorized without an
explicit human, and no away-mode/urgency/fear can override that.
"""
from __future__ import annotations

import itertools
import pytest

from sovereign_agent.integrity_sentinel import (
    REVERSIBLE_ACTIONS, IRREVERSIBLE_ACTIONS, FINDING_KINDS, SEVERITY,
    IntegrityFinding, IntegritySentinel,
)


def _alarmed():
    return IntegrityFinding(kind="suspicious_module", target="/lib/modules/x.ko",
                            anomaly_score=0.9, confidence=0.3, severity="critical",
                            evidence=["not in baseline"])


# ---- the safety invariant -------------------------------------------------

def test_reversible_actions_are_always_authorized():
    s = IntegritySentinel()
    for act in REVERSIBLE_ACTIONS:
        ok, _ = s.authorize(act)
        assert ok, f"reversible action {act} should be free"
        # ...even alone, in away mode, on an alarmed finding
        ok2, _ = s.authorize(act, away_mode=True, finding=_alarmed())
        assert ok2


def test_irreversible_actions_never_authorized_without_human():
    s = IntegritySentinel()
    f = _alarmed()
    extras = {"rm -rf /", "unknown_action", "format_disk"}  # unknown => fail safe
    for act, away in itertools.product(IRREVERSIBLE_ACTIONS | extras, (False, True)):
        ok, _ = s.authorize(act, human_authorized=False, away_mode=away, finding=f)
        assert ok is False, f"BREACH: {act} authorized autonomously (away={away})"


def test_irreversible_allowed_only_with_explicit_human():
    s = IntegritySentinel()
    for act in IRREVERSIBLE_ACTIONS:
        assert s.authorize(act, human_authorized=True)[0] is True


def test_fear_does_not_unlock_surgery():
    # 'fear' = high anomaly + low confidence; it must make the gate STRICTER, never looser.
    s = IntegritySentinel()
    f = _alarmed()
    assert f.is_alarmed
    ok, why = s.authorize("excise", human_authorized=False, away_mode=True, finding=f)
    assert ok is False
    assert "alarmed" in why or "panic" in why or "human" in why


def test_unknown_action_fails_safe_to_human():
    s = IntegritySentinel()
    assert s.authorize("something_new_and_scary")[0] is False


def test_sentinel_has_no_destructive_methods():
    # Read-only by construction: it senses, scores, recommends, gates — it does not act.
    destructive = (IRREVERSIBLE_ACTIONS | {"delete", "kill", "clean", "remove",
                                           "destroy", "overwrite"})
    assert not (destructive & set(dir(IntegritySentinel)))


# ---- sensing + advising ---------------------------------------------------

def test_observe_posts_a_transparent_notification():
    s = IntegritySentinel()
    note = s.observe(_alarmed())
    assert note.headline and note.detail
    assert note.severity == "critical"
    assert "snapshot_evidence" in note.recommendation.reversible_steps  # evidence preserved


def test_active_threat_recommends_reversible_containment_plus_gated_surgery():
    s = IntegritySentinel()
    rec = s.recommend(_alarmed())
    assert "alert" in rec.reversible_steps
    assert rec.irreversible_step is not None
    assert rec.requires_human is True
    # every reversible step is genuinely in the reversible set
    assert all(step in REVERSIBLE_ACTIONS for step in rec.reversible_steps)
    # the surgery step is genuinely irreversible
    assert rec.irreversible_step in IRREVERSIBLE_ACTIONS


def test_quiet_finding_just_observes():
    s = IntegritySentinel()
    f = IntegrityFinding(kind="new_file", target="/tmp/note.txt",
                         anomaly_score=0.1, confidence=0.9, severity="info")
    rec = s.recommend(f)
    assert rec.reversible_steps  # at least alert + snapshot
    assert rec.irreversible_step is None  # nothing to heal
    assert rec.requires_human is False


def test_unknown_finding_kind_raises():
    s = IntegritySentinel()
    with pytest.raises(ValueError):
        s.observe(IntegrityFinding(kind="not-a-kind"))


# ---- away mode ------------------------------------------------------------

def test_away_mode_contains_reversibly_and_queues_surgery():
    s = IntegritySentinel()
    resp = s.away_mode_response(_alarmed())
    assert resp["contained_reversibly"]                       # acted to stabilize
    assert all(a in REVERSIBLE_ACTIONS for a in resp["contained_reversibly"])
    assert resp["queued_for_human"] in IRREVERSIBLE_ACTIONS    # surgery waits
    assert resp["status"] == "awaiting_human"


def test_away_mode_with_no_surgery_just_contains():
    s = IntegritySentinel()
    f = IntegrityFinding(kind="new_file", target="/tmp/x", anomaly_score=0.1,
                         confidence=0.9, severity="info")
    resp = s.away_mode_response(f)
    assert resp["queued_for_human"] is None
    assert resp["status"] == "contained"


# ---- surface --------------------------------------------------------------

def test_pending_surgeries_and_acknowledge():
    s = IntegritySentinel()
    s.observe(_alarmed())
    assert len(s.pending_surgeries()) == 1
    assert s.snapshot()["awaiting_human_surgery"] == 1
    assert "Integrity Sentinel" in s.render()
    s.acknowledge(0)
    assert s.snapshot()["unacknowledged"] == 0


def test_constants_disjoint():
    # reversible and irreversible must never overlap — the gate depends on it.
    assert not (REVERSIBLE_ACTIONS & IRREVERSIBLE_ACTIONS)
    assert "freeze_process" in REVERSIBLE_ACTIONS and "kill_process" in IRREVERSIBLE_ACTIONS
