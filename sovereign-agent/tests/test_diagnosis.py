"""Tests for diagnosis — the Conflict Logic Catalog.

Covers the Conflict -> Diagnosis -> Resolution flow, the shared-actor timeline
(Kevin / Claude / Aria all keep the same notes), and the doctrine guards.
"""
from __future__ import annotations

import pytest

from sovereign_agent.diagnosis import (
    ACTORS, CONFLICT_TYPES, ConflictCatalog, CatalogError,
)


def test_full_flow_with_three_actors(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="contradiction",
                          trigger_event="memory said A; the live tool confirmed B at 02:14",
                          actor="claude", evidence=["log line 42"], severity="high")
    assert c.case_id.startswith("CL-")
    d = cat.diagnose(c.case_id, symptom_vs_cause="visible stale answer; cause is a stale cache",
                     confidence=0.85, root_cause="stale cache", actor="aria")
    assert d.status == "confirmed"  # confidence >= 0.80 + a root cause
    r = cat.resolve(c.case_id, fix_applied="invalidate cache on write",
                    rollback_plan="revert one commit", verification_result="confirmed",
                    actor="kevin")
    assert r.verification_result == "confirmed"
    assert cat.get_conflict(c.case_id).status == "resolved"
    # all three of us are on the timeline, in order
    actors = [e["actor"] for e in cat.timeline(c.case_id)]
    assert actors == ["claude", "aria", "kevin"]


def test_low_confidence_diagnosis_stays_open(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="drift", trigger_event="config that worked stopped working")
    d = cat.diagnose(c.case_id, symptom_vs_cause="x", confidence=0.4, root_cause="maybe")
    assert d.status == "open"


def test_open_conflict_requires_trigger(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError):
        cat.open_conflict(type="omission", trigger_event="   ")


def test_open_conflict_rejects_bad_type(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError):
        cat.open_conflict(type="not-a-type", trigger_event="something happened")


def test_resolve_requires_rollback_plan(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="cascade", trigger_event="a fix broke logging downstream")
    with pytest.raises(CatalogError):
        cat.resolve(c.case_id, fix_applied="patch", rollback_plan="")


def test_unknown_actor_rejected(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError):
        cat.open_conflict(type="ambiguity", trigger_event="prompt routed wrong",
                          actor="stranger")
    assert set(ACTORS) == {"kevin", "claude", "aria"}


def test_case_ids_increment(tmp_path):
    cat = ConflictCatalog(tmp_path)
    a = cat.open_conflict(type="contradiction", trigger_event="t1")
    b = cat.open_conflict(type="contradiction", trigger_event="t2")
    assert a.case_id == "CL-001" and b.case_id == "CL-002"


def test_timeline_is_append_only(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="drift", trigger_event="t")
    cat.diagnose(c.case_id, symptom_vs_cause="s", confidence=0.9, root_cause="rc")
    n1 = len(cat.timeline(c.case_id))
    cat.resolve(c.case_id, fix_applied="f", rollback_plan="r", verification_result="confirmed")
    n2 = len(cat.timeline(c.case_id))
    assert n2 > n1  # only ever grows


def test_stats_and_by_status(tmp_path):
    cat = ConflictCatalog(tmp_path)
    cat.open_conflict(type="contradiction", trigger_event="t1", actor="claude")
    c2 = cat.open_conflict(type="drift", trigger_event="t2", actor="aria")
    cat.diagnose(c2.case_id, symptom_vs_cause="s", confidence=0.9, root_cause="rc", actor="aria")
    s = cat.stats()
    assert s["total"] == 2
    assert s["by_type"]["contradiction"] == 1
    assert s["by_actor"]["aria"] == 1
    assert any(c.status == "diagnosing" for c in cat.by_status("diagnosing"))


def test_conflict_types_set():
    assert set(CONFLICT_TYPES) == {"contradiction", "drift", "ambiguity", "omission", "cascade"}


# ── Additional coverage for uncovered validation paths ─────────────────────


def test_open_conflict_rejects_bad_severity(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError, match="severity"):
        cat.open_conflict(type="drift", trigger_event="something", severity="catastrophic")


def test_open_conflict_rejects_bad_actor(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError, match="actor"):
        cat.open_conflict(type="drift", trigger_event="something", actor="nobody")


def test_diagnose_rejects_nonexistent_case(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError, match="no such case"):
        cat.diagnose("CL-999", symptom_vs_cause="x", confidence=0.5)


def test_diagnose_rejects_bad_actor(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="contradiction", trigger_event="something broke")
    with pytest.raises(CatalogError, match="actor"):
        cat.diagnose(c.case_id, symptom_vs_cause="x", actor="robot")


def test_resolve_rejects_nonexistent_case(tmp_path):
    cat = ConflictCatalog(tmp_path)
    with pytest.raises(CatalogError, match="no such case"):
        cat.resolve("CL-999", fix_applied="f", rollback_plan="r")


def test_resolve_rejects_bad_verification_result(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="drift", trigger_event="something")
    with pytest.raises(CatalogError, match="verification_result"):
        cat.resolve(c.case_id, fix_applied="f", rollback_plan="r",
                    verification_result="absolutely_certain")


def test_resolve_rejects_bad_actor(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="drift", trigger_event="something")
    with pytest.raises(CatalogError, match="actor"):
        cat.resolve(c.case_id, fix_applied="f", rollback_plan="r", actor="stranger")


def test_next_case_id_skips_non_numeric_fragments(tmp_path):
    """_next_case_id must not crash if a dir has a non-integer suffix."""
    cat = ConflictCatalog(tmp_path)
    # Manually create a case dir with a non-numeric suffix
    (tmp_path / "cases" / "CL-bad").mkdir(parents=True, exist_ok=True)
    # Should not raise — skips the bad name and starts from CL-001
    c = cat.open_conflict(type="contradiction", trigger_event="test")
    assert c.case_id == "CL-001"


def test_resolve_pending_verification_sets_resolving_status(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="cascade", trigger_event="things cascaded")
    cat.resolve(c.case_id, fix_applied="patch", rollback_plan="revert",
                verification_result="pending")
    assert cat.get_conflict(c.case_id).status == "resolving"


def test_resolve_partial_verification_sets_resolving_status(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="ambiguity", trigger_event="ambiguous routing")
    cat.resolve(c.case_id, fix_applied="clarify prompt", rollback_plan="revert change",
                verification_result="partial")
    assert cat.get_conflict(c.case_id).status == "resolving"


def test_policy_change_flag_propagates(tmp_path):
    cat = ConflictCatalog(tmp_path)
    c = cat.open_conflict(type="omission", trigger_event="missing validation step")
    r = cat.resolve(c.case_id, fix_applied="add gate", rollback_plan="remove gate",
                    policy_change_triggered=True, verification_result="confirmed")
    assert r.policy_change_triggered is True
