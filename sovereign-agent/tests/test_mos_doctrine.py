"""A 'Gym session' for the doctrine Kevin leans toward — exercising the new
canon clauses and the read-only priorities until they hold under load.

This is the fitness harness for *meaning*: it asserts the new patterns are
well-formed and discoverable, that the read-only priorities are genuinely
immutable at runtime ("no one can change them"), and that none of it disturbed
the invariants already baked into the canon (safety first, flourishing high).
"""
from __future__ import annotations

import dataclasses

import pytest

from sovereign_agent import mos_canon as mc

# The distinctive additions from Kevin's direction.
NEW_CLAUSE_IDS = [
    "mos-read-only-priorities",
    "mos-overkill-floor",
    "mos-advocate-pair",
    "mos-foresight-step",
    "mos-auditable-audits",
    "mos-intelligent-intuition",
    "mos-reflection-manifestation",
]


# ─── the new clauses are well-formed and discoverable ───────────────────────


@pytest.mark.parametrize("cid", NEW_CLAUSE_IDS)
def test_new_clause_present_and_well_formed(cid):
    c = mc.get_clause(cid)
    assert c is not None, f"{cid} missing from the canon"
    assert c.part in (
        "kernel", "workflow", "language", "architecture", "agentic",
        "command", "horizon", "implementation", "appendix",
    )
    # Every clause must carry real content in all three framing fields.
    assert len(c.principle.strip()) > 40
    assert len(c.leverage.strip()) > 20
    assert len(c.modulation.strip()) > 20
    assert c.examples, "a clause without examples isn't finished"
    # And the adaptive framing still wraps it.
    assert "Apply where it serves" in c.adaptive_framing()


def test_new_clauses_are_in_the_index_and_aggregate():
    for cid in NEW_CLAUSE_IDS:
        assert cid in mc.CLAUSE_INDEX
        assert any(c.id == cid for c in mc.ALL_CLAUSES)


def test_all_clause_ids_unique():
    ids = [c.id for c in mc.ALL_CLAUSES]
    assert len(ids) == len(set(ids))


def test_related_ids_resolve():
    """Every 'related' pointer on a new clause points at a real clause."""
    for cid in NEW_CLAUSE_IDS:
        c = mc.get_clause(cid)
        for rel in c.related:
            assert rel in mc.CLAUSE_INDEX, f"{cid} → unknown related {rel}"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("devil", "mos-advocate-pair"),
        ("angel", "mos-advocate-pair"),
        ("overkill", "mos-overkill-floor"),
        ("hypothesize", "mos-foresight-step"),
        ("pattern-match", "mos-foresight-step"),
        ("auditable", "mos-auditable-audits"),
        ("read-only", "mos-read-only-priorities"),
        ("intuition", "mos-intelligent-intuition"),
        ("articulation", "mos-reflection-manifestation"),
        ("mirror", "mos-reflection-manifestation"),
    ],
)
def test_search_surfaces_new_doctrine(query, expected):
    hits = {c.id for c in mc.search_clauses(query)}
    assert expected in hits, f"search({query!r}) did not surface {expected}"


# ─── the read-only priorities are real, and truly immutable ─────────────────


def test_three_read_only_priorities_present():
    P = mc.read_only_priorities()
    names = [p.name for p in P]
    assert names == ["Safety", "Love", "Flourishing"]


def test_flourishing_names_coexistence_and_coevolution():
    P = mc.read_only_priorities()
    flourishing = P.by_name("Flourishing")
    assert flourishing is not None
    text = flourishing.statement.lower()
    assert "coexistence" in text
    assert "coevolution" in text


def test_priority_items_are_frozen():
    """A priority's fields cannot be reassigned (no quiet rewrite of 'Safety')."""
    P = mc.read_only_priorities()
    with pytest.raises(dataclasses.FrozenInstanceError):
        P[0].name = "Convenience"  # type: ignore[misc]


def test_priority_collection_rejects_item_assignment():
    P = mc.read_only_priorities()
    with pytest.raises((TypeError, AttributeError)):
        P[0] = mc.ReadOnlyPriority("X", "y")  # type: ignore[index]


def test_priority_collection_rejects_new_attributes():
    P = mc.read_only_priorities()
    with pytest.raises(AttributeError):
        P.extra = "nope"  # type: ignore[attr-defined]


def test_priority_collection_has_no_mutators():
    """It's a tuple subclass — none of list's in-place mutators exist."""
    P = mc.read_only_priorities()
    for mutator in ("append", "extend", "insert", "pop", "remove", "clear", "sort"):
        assert not hasattr(P, mutator), f"read-only priorities should not expose {mutator}"


def test_statement_renders_all_three():
    s = mc.read_only_priorities().statement().lower()
    assert "safety" in s and "love" in s and "flourishing" in s


# ─── the additions didn't disturb the existing invariants ───────────────────


def test_priority_stack_still_safety_first():
    ps = mc.get_clause("mos-priority-stack")
    assert ps is not None
    head = ps.principle.split("(2)")[0]
    assert "Safety" in head  # safety is still tier 1


def test_adaptive_framing_unchanged():
    assert "Love and flourishing across generations is the priority." in mc.ADAPTIVE_FRAMING


def test_canon_still_grows_not_cages():
    """Spot-check the doctrine's stance survived: clauses carry modulation
    (how to soften/skip), i.e. patterns, not cages."""
    for c in mc.ALL_CLAUSES:
        assert c.modulation.strip(), f"{c.id} lost its modulation (the 'not a cage' half)"
