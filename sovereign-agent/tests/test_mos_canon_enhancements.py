"""Gym session for the 2026-08-02 Omnibus Canon enhancement round — mirrors
test_mos_doctrine.py's own shape from the prior round ("Kevin's direction").

Grounded in a research pass over Kevin's ARIA_OMNIBUS_CANON.md
(~/Downloads/Omnibus/) cross-checked against the live codebase: 11 new
clauses, 2 previously-empty PartId slots (command/implementation)
populated, 2 existing clauses sharpened additively (mos-angels-advocate,
mos-idempotency — not re-tested here as "new", their pre-existing tests
in test_mos_doctrine.py already cover them). Explicitly does NOT touch
READ_ONLY_PRIORITIES or anything DEFERRED_UNSAFE-adjacent.
"""
from __future__ import annotations

import pytest

from sovereign_agent import mos_canon as mc

OMNIBUS_2026_08_CLAUSE_IDS = [
    "mos-verification-quartet",
    "mos-lesson-capture",
    "mos-seven-block-transmit",
    "mos-evidence-tiers",
    "mos-outbound-sovereignty",
    "mos-continuity-of-care",
    "mos-proactive-handoff",
    "mos-secret-zero",
    "mos-subagent-isolation",
    "mos-command-protocol-zero",
    "mos-command-just-audit",
    "mos-implementation-profiles",
]


@pytest.mark.parametrize("cid", OMNIBUS_2026_08_CLAUSE_IDS)
def test_new_clause_present_and_well_formed(cid):
    c = mc.get_clause(cid)
    assert c is not None, f"{cid} missing from the canon"
    assert c.part in (
        "kernel", "workflow", "language", "architecture", "agentic",
        "command", "horizon", "implementation", "appendix",
    )
    assert len(c.principle.strip()) > 40
    assert len(c.leverage.strip()) > 20
    assert len(c.modulation.strip()) > 20
    assert c.examples, "a clause without examples isn't finished"
    assert "Apply where it serves" in c.adaptive_framing()


def test_new_clauses_are_in_the_index_and_aggregate():
    for cid in OMNIBUS_2026_08_CLAUSE_IDS:
        assert cid in mc.CLAUSE_INDEX
        assert any(c.id == cid for c in mc.ALL_CLAUSES)


def test_related_ids_resolve():
    for cid in OMNIBUS_2026_08_CLAUSE_IDS:
        c = mc.get_clause(cid)
        for rel in c.related:
            assert rel in mc.CLAUSE_INDEX, f"{cid} → unknown related {rel}"


def test_command_and_implementation_parts_are_no_longer_empty():
    """Both PartIds were declared in the type since this module's first
    version with zero clauses ever filed — closing that structural gap."""
    assert mc.clauses_by_part("command")
    assert mc.clauses_by_part("implementation")


def test_all_clause_ids_still_unique_after_the_batch():
    ids = [c.id for c in mc.ALL_CLAUSES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "query,expected",
    [
        ("verification quartet", "mos-verification-quartet"),
        ("confidence-gated", "mos-lesson-capture"),
        ("seven-block", "mos-seven-block-transmit"),
        ("evidence-grading", "mos-evidence-tiers"),
        ("outbound", "mos-outbound-sovereignty"),
        ("continuity of care", "mos-continuity-of-care"),
        ("budget ceiling", "mos-proactive-handoff"),
        ("secret zero", "mos-secret-zero"),
        ("sub-agent isolation", "mos-subagent-isolation"),
        ("redteam", "mos-command-just-audit"),
        ("sovereign local", "mos-implementation-profiles"),
    ],
)
def test_search_surfaces_new_doctrine(query, expected):
    hits = {c.id for c in mc.search_clauses(query)}
    assert expected in hits, f"search({query!r}) did not surface {expected}"


def test_deferred_unsafe_boundary_untouched():
    """Explicit exclusions from the plan — none of these were ported."""
    haystack = " ".join(
        c.principle + c.leverage + c.modulation for c in mc.ALL_CLAUSES
    ).lower()
    for banned in ("self-taught reasoning", "star level 2", "star level 3",
                  "architectural rebalancing", "fine-tun"):
        assert banned not in haystack, f"DEFERRED_UNSAFE-adjacent content leaked in: {banned!r}"


def test_read_only_priorities_still_exactly_three_and_unchanged():
    names = [p.name for p in mc.READ_ONLY_PRIORITIES]
    assert names == ["Safety", "Love", "Flourishing"]


def test_mos_canon_ingest_planner_covers_the_full_new_count():
    from sovereign_agent.planners.mos_canon_ingest import MOSCanonIngestPlanner

    result = MOSCanonIngestPlanner().plan()
    assert len(result.steps) == len(mc.ALL_CLAUSES)
