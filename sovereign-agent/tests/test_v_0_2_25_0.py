"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_25_0.py — The Garden                                          ║
║                                                                           ║
║  Tests for:                                                               ║
║    1. Pure composition operators (union, intersection, specialize,       ║
║       generalize) — deterministic, palimpsest-preserving                 ║
║    2. The LLM-driven architect operator — proposals filtered through    ║
║       the same disciplines as discovery (no hallucinated parents, etc.) ║
║    3. Memory garden survey — read-only, never blocks                   ║
║    4. Reorganization pass — safe operations only                       ║
║    5. The 1000-memory trigger signal                                   ║
║                                                                           ║
║  Invariants:                                                             ║
║    • Composition never deletes parents                                  ║
║    • Composed patterns start with FRESH OutcomeMetrics                  ║
║    • Composed patterns reference parents by ID (lineage preserved)     ║
║    • Reorganization is non-destructive (no deletes, no merges)        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── Pure composition operators ────────────────────────────────────────────


def _make_pattern(**kwargs):
    from sovereign_agent.stewardship.behavior import (
        BehaviorPattern, TriggerConditions, OutcomeMetrics,
    )
    defaults = {
        "name": "test",
        "description": "x",
        "trigger": TriggerConditions(),
        "action_shape": "y",
        "outcome": OutcomeMetrics(),
    }
    defaults.update(kwargs)
    return BehaviorPattern(**defaults)


class TestCompositionOperators:

    def test_union_broadens_channels_any(self):
        from sovereign_agent.stewardship.architect import compose_union
        from sovereign_agent.stewardship.behavior import TriggerConditions
        a = _make_pattern(name="a",
            trigger=TriggerConditions(channels_any=["x", "y"]))
        b = _make_pattern(name="b",
            trigger=TriggerConditions(channels_any=["y", "z"]))
        u = compose_union(a, b)
        assert set(u.trigger.channels_any) == {"x", "y", "z"}

    def test_intersection_narrows_channels_any(self):
        from sovereign_agent.stewardship.architect import compose_intersection
        from sovereign_agent.stewardship.behavior import TriggerConditions
        a = _make_pattern(name="a",
            trigger=TriggerConditions(channels_any=["x", "y"]))
        b = _make_pattern(name="b",
            trigger=TriggerConditions(channels_any=["y", "z"]))
        i = compose_intersection(a, b)
        # Intersection of channels_any: must overlap both = {y}
        assert set(i.trigger.channels_any) == {"y"}

    def test_specialize_adds_constraints(self):
        from sovereign_agent.stewardship.architect import specialize
        from sovereign_agent.stewardship.behavior import TriggerConditions
        parent = _make_pattern(name="parent",
            trigger=TriggerConditions(channels_any=["x"]))
        s = specialize(parent,
            additional_trigger=TriggerConditions(text_contains_any=["pain"]))
        assert "pain" in s.trigger.text_contains_any
        assert "x" in s.trigger.channels_any

    def test_generalize_drops_constraint(self):
        from sovereign_agent.stewardship.architect import generalize
        from sovereign_agent.stewardship.behavior import TriggerConditions
        parent = _make_pattern(name="p",
            trigger=TriggerConditions(
                channels_any=["x"],
                authority_tier_max=0,
            ))
        g = generalize(parent, drop_field="authority_tier_max")
        assert g.trigger.authority_tier_max is None
        # Other constraints preserved
        assert "x" in g.trigger.channels_any

    def test_composed_pattern_has_fresh_outcome(self):
        """Composed patterns must start with zero observations — they
        earn their valuable status through new evidence."""
        from sovereign_agent.stewardship.architect import compose_union
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, OutcomeMetrics,
        )
        # Parents have non-trivial outcomes
        out_a = OutcomeMetrics()
        for _ in range(10):
            out_a.update_honor(0.9)
        a = _make_pattern(name="a", outcome=out_a,
            trigger=TriggerConditions(channels_any=["x"]))
        b = _make_pattern(name="b", outcome=out_a,
            trigger=TriggerConditions(channels_any=["y"]))
        u = compose_union(a, b)
        assert u.outcome.honor_n == 0
        assert u.outcome.calibration_n == 0
        assert not u.outcome.is_valuable

    def test_composed_pattern_lineage_preserved(self):
        from sovereign_agent.stewardship.architect import (
            compose_union, compose_intersection, specialize, generalize,
        )
        from sovereign_agent.stewardship.behavior import TriggerConditions
        a = _make_pattern(name="a",
            trigger=TriggerConditions(channels_any=["x"]))
        b = _make_pattern(name="b",
            trigger=TriggerConditions(channels_any=["y"]))
        u = compose_union(a, b)
        assert a.pattern_id in u.parents
        assert b.pattern_id in u.parents
        s = specialize(a, additional_trigger=TriggerConditions(
            text_contains_any=["x"]))
        assert a.pattern_id in s.parents

    def test_composition_tags_include_marker(self):
        from sovereign_agent.stewardship.architect import compose_union
        from sovereign_agent.stewardship.behavior import TriggerConditions
        a = _make_pattern(name="a",
            trigger=TriggerConditions(channels_any=["x"]),
            tags=["existing"])
        b = _make_pattern(name="b",
            trigger=TriggerConditions(channels_any=["y"]),
            tags=["another"])
        u = compose_union(a, b)
        assert "composed" in u.tags
        assert "union" in u.tags
        # Parent tags preserved
        assert "existing" in u.tags

    def test_specialize_with_intent_kind_added(self):
        from sovereign_agent.stewardship.architect import specialize
        from sovereign_agent.stewardship.behavior import TriggerConditions
        parent = _make_pattern(
            trigger=TriggerConditions(channels_any=["x"])
        )
        s = specialize(parent, additional_trigger=TriggerConditions(
            intent_kind="Conversation"))
        assert s.trigger.intent_kind == "Conversation"


# ─── Architect operator (LLM-driven) ───────────────────────────────────────


def _mock_architect_client(compositions_response):
    client = MagicMock()
    client.chat = AsyncMock(return_value={
        "message": {"role": "assistant",
                     "content": json.dumps(compositions_response)}
    })
    return client


def _make_eligible_parent(name, channels, store, *, honor_n=5):
    """Build a pattern with enough evidence to be eligible as a parent."""
    from sovereign_agent.stewardship.behavior import (
        BehaviorPattern, TriggerConditions, OutcomeMetrics,
    )
    outcome = OutcomeMetrics()
    for _ in range(honor_n):
        outcome.update_honor(0.8)
        outcome.update_calibration(0.7)
    p = BehaviorPattern(
        name=name, description=f"pattern {name}",
        trigger=TriggerConditions(channels_any=channels),
        action_shape="default action",
        outcome=outcome,
    )
    store.append(p)
    return p


class TestArchitectOperator:

    def test_offline_is_no_op(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        _make_eligible_parent("a", ["x"], store)
        _make_eligible_parent("b", ["y"], store)
        summary = asyncio.run(architect_patterns(
            ollama_client=None,
            pattern_store=store,
        ))
        assert summary["skipped_offline"] is True
        assert summary["compositions_saved"] == 0

    def test_no_op_when_fewer_than_two_eligible(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        _make_eligible_parent("a", ["x"], store)   # only one
        client = _mock_architect_client({"compositions": []})
        summary = asyncio.run(architect_patterns(
            ollama_client=client,
            pattern_store=store,
        ))
        assert summary["compositions_saved"] == 0
        # Eligible count is 1
        assert summary["eligible_parents"] == 1

    def test_valid_union_composition_saved(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        a = _make_eligible_parent("alpha", ["x"], store)
        b = _make_eligible_parent("beta", ["y"], store)

        client = _mock_architect_client({
            "compositions": [{
                "kind": "union",
                "parent_ids": [a.pattern_id, b.pattern_id],
                "name": "alpha-or-beta",
                "description": "fires for either",
                "rationale": "same action shape, complementary triggers",
            }]
        })

        summary = asyncio.run(architect_patterns(
            ollama_client=client,
            pattern_store=store,
        ))
        assert summary["compositions_saved"] == 1
        named = [p for p in store.active() if p.name == "alpha-or-beta"]
        assert len(named) == 1
        assert "composed" in named[0].tags
        assert "union" in named[0].tags

    def test_hallucinated_parent_rejected(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        _make_eligible_parent("a", ["x"], store)
        _make_eligible_parent("b", ["y"], store)

        client = _mock_architect_client({
            "compositions": [{
                "kind": "union",
                "parent_ids": ["fake-id-1", "fake-id-2"],
                "name": "ghost",
                "description": "from nowhere",
            }]
        })
        summary = asyncio.run(architect_patterns(
            ollama_client=client,
            pattern_store=store,
        ))
        assert summary["compositions_saved"] == 0

    def test_low_evidence_parents_excluded_from_eligibility(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        # Both parents have only 1 observation — below threshold
        _make_eligible_parent("a", ["x"], store, honor_n=1)
        _make_eligible_parent("b", ["y"], store, honor_n=1)
        client = _mock_architect_client({"compositions": []})
        summary = asyncio.run(architect_patterns(
            ollama_client=client,
            pattern_store=store,
            min_evidence_per_parent=3,
        ))
        assert summary["eligible_parents"] == 0

    def test_specialize_with_empty_additional_dropped(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        a = _make_eligible_parent("a", ["x"], store)
        _make_eligible_parent("b", ["y"], store)  # need ≥2 to call LLM

        client = _mock_architect_client({
            "compositions": [{
                "kind": "specialize",
                "parent_ids": [a.pattern_id],
                "name": "empty-spec",
                "description": "no actual constraint added",
                "specialize_add": {},   # empty!
            }]
        })
        summary = asyncio.run(architect_patterns(
            ollama_client=client,
            pattern_store=store,
        ))
        assert summary["compositions_saved"] == 0

    def test_duplicate_name_not_saved(self, tmp_path):
        from sovereign_agent.stewardship.architect import architect_patterns
        from sovereign_agent.stewardship.behavior import (
            BehaviorPatternStore, BehaviorPattern, TriggerConditions,
        )
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        a = _make_eligible_parent("a", ["x"], store)
        b = _make_eligible_parent("b", ["y"], store)
        # Pre-existing pattern with the name the LLM will propose
        store.append(BehaviorPattern(
            name="alpha-beta-union",
            description="already here",
            trigger=TriggerConditions(channels_any=["z"]),
        ))

        client = _mock_architect_client({
            "compositions": [{
                "kind": "union",
                "parent_ids": [a.pattern_id, b.pattern_id],
                "name": "alpha-beta-union",
                "description": "duplicate",
            }]
        })
        summary = asyncio.run(architect_patterns(
            ollama_client=client,
            pattern_store=store,
        ))
        assert summary["compositions_saved"] == 0


# ─── Memory garden ─────────────────────────────────────────────────────────


class TestMemorySurvey:

    def test_empty_data_dir_survey_does_not_raise(self, tmp_path):
        from sovereign_agent.stewardship.memory_garden import survey_memory
        health = survey_memory(tmp_path)
        assert health.total_memories == 0
        assert health.atoms_active == 0
        assert health.patterns_active == 0

    def test_atom_count_reflects_active_only(self, tmp_path):
        from sovereign_agent.stewardship.atoms import (
            Atom, AtomStore, AtomKind,
        )
        from sovereign_agent.stewardship.memory_garden import survey_memory
        store = AtomStore(tmp_path / "atoms.ndjson")
        a1 = Atom(kind=AtomKind.FACT, title="active 1", claim="x",
                   evidence_refs=["e1", "e2"])
        a2 = Atom(kind=AtomKind.FACT, title="active 2", claim="y",
                   evidence_refs=["e1", "e2"])
        a3 = Atom(kind=AtomKind.FACT, title="will be superseded", claim="z",
                   evidence_refs=["e1", "e2"])
        store.append(a1)
        store.append(a2)
        store.append(a3)
        new = Atom(title="replacement", claim="x",
                    evidence_refs=["e1", "e2"])
        store.supersede(a3.atom_id, new)
        health = survey_memory(tmp_path)
        assert health.atoms_active == 3   # a1, a2, new
        assert health.atoms_total == 4    # plus superseded a3

    def test_atoms_db_writes_are_visible_too(self, tmp_path):  # atoms-db-visibility-d
        """Kevin, 2026-07-21: "I never see any of that increase. I never
        see atoms increase... she said something about updating memory a
        couple of times." Root cause: memory_write (the only tool she
        actually has for this) writes to atoms.db via memory.write_atom,
        a completely different store from the atoms.ndjson AtomStore
        reads above -- every real write was invisible to this pane. Uses
        the SAME real write_atom() call path memory_write.py's tool
        calls, not a hand-built row, so this proves the actual bug is
        fixed, not a stand-in for it."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.db import open_atoms_db
        from sovereign_agent.memory import Atom, write_atom
        from sovereign_agent.stewardship.memory_garden import survey_memory

        # isolated_paths (conftest, autouse) already points SETTINGS.paths
        # at tmp_path-equivalent dirs -- use that same data_dir so
        # open_atoms_db() and survey_memory() agree on where atoms.db is.
        data_dir = SETTINGS.paths.data_dir
        before = survey_memory(data_dir)

        conn = open_atoms_db()
        try:
            write_atom(conn, Atom(
                type="observation", summary="a real memory_write-shaped atom",
                content_ref={"kind": "inline", "content": "hello"},
                claims=[], parents=["evt_1"], confidence=0.9,
                created_by={"actor": "agent", "model": "test", "version": "0.2.1"},
            ))
            conn.commit()
        finally:
            conn.close()

        after = survey_memory(data_dir)
        assert after.atoms_total == before.atoms_total + 1
        assert after.atoms_active == before.atoms_active + 1

    def test_pattern_counts(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore,
            PatternStatus, TriggerConditions, OutcomeMetrics,
        )
        from sovereign_agent.stewardship.memory_garden import survey_memory
        store = BehaviorPatternStore(tmp_path / "behavior-patterns.ndjson")
        # Active pattern
        store.append(BehaviorPattern(name="active1", description="x",
                                       trigger=TriggerConditions(channels_any=["a"])))
        # Active and valuable
        out = OutcomeMetrics()
        for _ in range(5):
            out.update_honor(0.8)
            out.update_calibration(0.8)
            out.update_survival(True)
        store.append(BehaviorPattern(name="valuable1", description="y",
                                       trigger=TriggerConditions(channels_any=["b"]),
                                       outcome=out))
        # Dormant
        store.append(BehaviorPattern(name="dormant1", description="z",
                                       trigger=TriggerConditions(channels_any=["c"]),
                                       status=PatternStatus.DORMANT))
        health = survey_memory(tmp_path)
        assert health.patterns_active == 2
        assert health.patterns_dormant == 1
        assert health.patterns_valuable == 1

    def test_hot_channels_extracted_from_atoms(self, tmp_path):
        from sovereign_agent.stewardship.atoms import Atom, AtomStore
        from sovereign_agent.stewardship.memory_garden import survey_memory
        store = AtomStore(tmp_path / "atoms.ndjson")
        for i in range(5):
            store.append(Atom(
                title=f"a{i}", claim="x",
                channels=["back-pain", "emotions"],
                evidence_refs=["e1", "e2"],
            ))
        for i in range(3):
            store.append(Atom(
                title=f"b{i}", claim="y",
                channels=["identity"],
                evidence_refs=["e1", "e2"],
            ))
        health = survey_memory(tmp_path)
        hot = dict(health.hot_channels)
        assert hot["back-pain"] == 5
        assert hot["emotions"] == 5
        assert hot["identity"] == 3

    def test_duplicate_atoms_detected(self, tmp_path):
        from sovereign_agent.stewardship.atoms import Atom, AtomStore
        from sovereign_agent.stewardship.memory_garden import survey_memory
        store = AtomStore(tmp_path / "atoms.ndjson")
        # Two atoms with same channels and overlapping evidence
        store.append(Atom(
            title="dup1", claim="x",
            channels=["back-pain"],
            evidence_refs=["e1", "e2", "e3"],
        ))
        store.append(Atom(
            title="dup2", claim="y",
            channels=["back-pain"],
            evidence_refs=["e2", "e3", "e4"],
        ))
        health = survey_memory(tmp_path)
        assert len(health.duplicate_atom_suggestions) >= 1

    def test_reorganization_threshold(self, tmp_path):
        from sovereign_agent.stewardship.memory_garden import MemoryHealth
        small = MemoryHealth(total_memories=500)
        large = MemoryHealth(total_memories=1500)
        assert not small.needs_reorganization()
        assert large.needs_reorganization()


# ─── Reorganization pass ───────────────────────────────────────────────────


class TestReorganization:

    def test_dormancy_sweep_marks_stale_patterns_dormant(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore,
            PatternStatus, TriggerConditions,
        )
        from sovereign_agent.stewardship.memory_garden import reorganize
        store = BehaviorPatternStore(tmp_path / "behavior-patterns.ndjson")
        # Append a fresh pattern
        fresh = BehaviorPattern(name="fresh", description="x",
                                  trigger=TriggerConditions(channels_any=["a"]))
        store.append(fresh)
        # Now manually write a stale pattern's record directly to the log
        # (bypassing append, which would update ts_last_obs to now).
        import json as _json
        from dataclasses import asdict
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(
            timespec="seconds")
        stale = BehaviorPattern(name="stale", description="y",
                                  trigger=TriggerConditions(channels_any=["b"]),
                                  ts_last_obs=old_ts,
                                  ts_first_obs=old_ts)
        with (tmp_path / "behavior-patterns.ndjson").open("a") as f:
            f.write(_json.dumps(asdict(stale), default=str) + "\n")
        store.invalidate()   # force re-read

        result = reorganize(tmp_path, dormancy_days=30)
        # The stale one should be marked dormant
        all_patterns = {p.name: p for p in store.all_patterns()}
        assert all_patterns["stale"].status == PatternStatus.DORMANT
        assert all_patterns["fresh"].status == PatternStatus.ACTIVE
        assert result.patterns_marked_dormant == 1

    def test_reorganize_does_not_delete_anything(self, tmp_path):
        """The reorganization is non-destructive — count before equals
        count after for the log files."""
        from sovereign_agent.stewardship.atoms import Atom, AtomStore
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, TriggerConditions,
        )
        from sovereign_agent.stewardship.memory_garden import reorganize
        atoms = AtomStore(tmp_path / "atoms.ndjson")
        for i in range(3):
            atoms.append(Atom(title=f"a{i}", claim="x",
                                evidence_refs=["e1", "e2"]))
        patterns = BehaviorPatternStore(tmp_path / "behavior-patterns.ndjson")
        for i in range(3):
            patterns.append(BehaviorPattern(
                name=f"p{i}", description="x",
                trigger=TriggerConditions(channels_any=[str(i)]),
            ))
        atom_lines_before = sum(1 for _ in (tmp_path / "atoms.ndjson").open())
        pattern_lines_before = sum(1 for _ in
            (tmp_path / "behavior-patterns.ndjson").open())
        reorganize(tmp_path)
        atom_lines_after = sum(1 for _ in (tmp_path / "atoms.ndjson").open())
        # Atoms file untouched
        assert atom_lines_after == atom_lines_before
        # Patterns file may grow (dormancy entries appended) but no
        # lines deleted
        pattern_lines_after = sum(1 for _ in
            (tmp_path / "behavior-patterns.ndjson").open())
        assert pattern_lines_after >= pattern_lines_before

    def test_reorganize_returns_suggestions(self, tmp_path):
        from sovereign_agent.stewardship.atoms import Atom, AtomStore
        from sovereign_agent.stewardship.memory_garden import reorganize
        atoms = AtomStore(tmp_path / "atoms.ndjson")
        # Two atoms with overlapping evidence → duplicate suggestion
        atoms.append(Atom(title="dup1", claim="x",
                            channels=["back-pain"],
                            evidence_refs=["e1", "e2", "e3"]))
        atoms.append(Atom(title="dup2", claim="y",
                            channels=["back-pain"],
                            evidence_refs=["e1", "e2", "e3"]))
        result = reorganize(tmp_path)
        # Suggestions surfaced (not auto-merged)
        assert len(result.suggestions_for_operator) >= 1


# ─── Doctrine: nothing deleted, palimpsest enforced ────────────────────────


class TestPalimpsestEnforcement:

    def test_memory_garden_module_has_no_delete_functions(self):
        from sovereign_agent.stewardship import memory_garden
        for name in dir(memory_garden):
            assert not name.startswith("delete_")
            assert not name.startswith("remove_")
            assert "destroy" not in name.lower()

    def test_architect_module_has_no_delete_functions(self):
        from sovereign_agent.stewardship import architect
        for name in dir(architect):
            assert not name.startswith("delete_")
            assert not name.startswith("remove_")
            assert "destroy" not in name.lower()
