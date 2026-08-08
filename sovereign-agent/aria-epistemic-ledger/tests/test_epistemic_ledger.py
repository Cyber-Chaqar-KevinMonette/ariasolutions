"""Behavior tests for aria-epistemic-ledger — prove beliefs write+read back,
revision chains preserve history (palimpsest discipline: nothing is ever
mutated or deleted), and the uncertainty registry opens/closes correctly."""
from __future__ import annotations

import pytest

from sovereign_agent.epistemic_ledger import EpistemicLedger, UncertaintyRegistry


# ─── beliefs: write + read back ─────────────────────────────────────────────

def test_record_and_read_back(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    belief = ledger.record("the sky is blue", 0.95, evidence_refs=["atom-123"])
    assert belief.confidence == 0.95
    assert belief.evidence_refs == ["atom-123"]

    fetched = ledger.get(belief.belief_id)
    assert fetched is not None
    assert fetched.claim == "the sky is blue"


def test_state_survives_reconstruction(tmp_path):
    """A fresh EpistemicLedger reading the same on-disk log sees identical state."""
    ledger1 = EpistemicLedger(tmp_path)
    b = ledger1.record("water is wet", 0.99)
    ledger2 = EpistemicLedger(tmp_path)
    assert ledger2.get(b.belief_id).claim == "water is wet"


# ─── revision: palimpsest discipline ────────────────────────────────────────

def test_revise_appends_never_mutates(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    original = ledger.record("the earth is flat", 0.3, evidence_refs=["atom-1"])
    revised = ledger.revise(original.belief_id, "the earth is round", "new evidence arrived",
                             confidence=0.99, evidence_refs=["atom-2", "atom-3"])

    # the old belief is untouched and still readable
    still_there = ledger.get(original.belief_id)
    assert still_there.claim == "the earth is flat"
    assert still_there.confidence == 0.3

    # the new belief points back
    assert revised.revised_from == original.belief_id
    assert revised.claim == "the earth is round"
    assert revised.confidence == 0.99


def test_revise_of_nonexistent_belief_raises(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    with pytest.raises(ValueError):
        ledger.revise("belief-does-not-exist", "x", "reason")


def test_lineage_returns_full_chain_oldest_first(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    b1 = ledger.record("v1", 0.2)
    b2 = ledger.revise(b1.belief_id, "v2", "update 1")
    b3 = ledger.revise(b2.belief_id, "v3", "update 2")

    chain = ledger.lineage(b3.belief_id)
    assert [b.claim for b in chain] == ["v1", "v2", "v3"]


def test_current_beliefs_shows_only_lineage_tips(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    independent = ledger.record("unrelated fact", 0.8)
    b1 = ledger.record("v1", 0.2)
    ledger.revise(b1.belief_id, "v2", "update")

    current = {b.claim for b in ledger.current_beliefs()}
    assert current == {"unrelated fact", "v2"}   # "v1" is superseded, not current


def test_all_beliefs_never_shrinks_after_revision(tmp_path):
    """Nothing is ever deleted from the log — a hard palimpsest guarantee."""
    ledger = EpistemicLedger(tmp_path)
    b1 = ledger.record("v1", 0.2)
    ledger.revise(b1.belief_id, "v2", "update")
    ledger.revise(b1.belief_id, "v2-alt", "a second, different revision of v1")

    assert len(ledger.all_beliefs()) == 3  # v1, v2, v2-alt — all preserved


# ─── uncertainty registry ────────────────────────────────────────────────────

def test_open_and_list(tmp_path):
    registry = UncertaintyRegistry(tmp_path)
    u = registry.open("cosmology", "why does time move forward", "no consensus theory")
    assert u.is_open
    assert [x.uncertainty_id for x in registry.list_open()] == [u.uncertainty_id]


def test_close_removes_from_open_but_keeps_in_all(tmp_path):
    registry = UncertaintyRegistry(tmp_path)
    u = registry.open("cosmology", "why does time move forward", "no consensus theory")
    closed = registry.close(u.uncertainty_id, "resolved: entropy gradient hypothesis accepted")

    assert closed.is_open is False
    assert registry.list_open() == []
    assert len(registry.list_all()) == 1
    assert registry.list_all()[0].resolution == "resolved: entropy gradient hypothesis accepted"


def test_close_of_nonexistent_raises(tmp_path):
    registry = UncertaintyRegistry(tmp_path)
    with pytest.raises(ValueError):
        registry.close("unc-does-not-exist", "resolution")


def test_state_survives_reconstruction_for_uncertainties(tmp_path):
    registry1 = UncertaintyRegistry(tmp_path)
    u = registry1.open("x", "q", "why")
    registry2 = UncertaintyRegistry(tmp_path)
    assert len(registry2.list_open()) == 1
    assert registry2.list_open()[0].uncertainty_id == u.uncertainty_id


def test_corrupt_log_line_is_skipped_not_fatal(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    ledger.record("real belief", 0.5)
    with open(ledger.log, "a", encoding="utf-8") as fh:
        fh.write("{ not valid json\n")
    assert len(ledger.all_beliefs()) == 1
