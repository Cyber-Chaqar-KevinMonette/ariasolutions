"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_23_0.py — atoms, consolidation, palimpsest discipline         ║
║                                                                           ║
║  The core invariants tested here:                                         ║
║                                                                           ║
║    1. Atoms are append-only; supersession preserves history.             ║
║    2. Clustering is deterministic and channel-set-based.                 ║
║    3. Consolidation is no-op when the LLM is unavailable.                ║
║    4. The LLM's atom proposals are filtered: < 2 evidence refs → drop.  ║
║    5. Palimpsest: atoms point to provenance entry IDs that can be       ║
║       resolved back to the original entries.                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Atom CRUD and palimpsest ──────────────────────────────────────────────


class TestAtomStore:

    def test_append_and_active(self, tmp_path):
        from sovereign_agent.stewardship.atoms import (
            Atom, AtomKind, AtomStore,
        )
        store = AtomStore(tmp_path / "atoms.ndjson")
        a1 = Atom(kind=AtomKind.FACT, title="fact 1", claim="x",
                   evidence_refs=["e1", "e2"])
        a2 = Atom(kind=AtomKind.PATTERN, title="pattern 1", claim="y",
                   evidence_refs=["e3", "e4"])
        store.append(a1)
        store.append(a2)
        active = store.active()
        assert len(active) == 2
        titles = {a.title for a in active}
        assert "fact 1" in titles
        assert "pattern 1" in titles

    def test_supersede_preserves_history(self, tmp_path):
        """The palimpsest: supersession doesn't delete the original
        entry. It writes update entries and the original raw line is
        still in the file."""
        from sovereign_agent.stewardship.atoms import (
            Atom, AtomKind, AtomStatus, AtomStore,
        )
        store = AtomStore(tmp_path / "atoms.ndjson")
        old = Atom(kind=AtomKind.FACT, title="old", claim="x",
                    evidence_refs=["e1", "e2"])
        store.append(old)
        new = Atom(kind=AtomKind.FACT, title="new", claim="y",
                    evidence_refs=["e1", "e2", "e3"])
        store.supersede(old.atom_id, new)
        # Active: only new
        active = store.active()
        assert len(active) == 1
        assert active[0].atom_id == new.atom_id
        # Raw log: old, status-update, new — three lines minimum
        raw = list(store.iter_raw())
        assert len(raw) >= 3
        # Old atom history is recoverable
        old_states = [a for a in raw if a.atom_id == old.atom_id]
        # First state is active, last state is superseded
        assert old_states[0].status == AtomStatus.ACTIVE
        assert old_states[-1].status == AtomStatus.SUPERSEDED

    def test_confidence_clamped(self):
        from sovereign_agent.stewardship.atoms import Atom, AtomKind
        a = Atom(confidence=2.0)
        assert a.confidence == 1.0
        a = Atom(confidence=-0.5)
        assert a.confidence == 0.0

    def test_search_by_kind(self, tmp_path):
        from sovereign_agent.stewardship.atoms import (
            Atom, AtomKind, AtomStore,
        )
        store = AtomStore(tmp_path / "atoms.ndjson")
        store.append(Atom(kind=AtomKind.FACT, title="f1", claim="",
                            evidence_refs=["a", "b"]))
        store.append(Atom(kind=AtomKind.PATTERN, title="p1", claim="",
                            evidence_refs=["a", "b"]))
        store.append(Atom(kind=AtomKind.RULE, title="r1", claim="",
                            evidence_refs=["a", "b"]))
        facts = store.search(kind=AtomKind.FACT)
        patterns = store.search(kind=AtomKind.PATTERN)
        assert len(facts) == 1 and facts[0].title == "f1"
        assert len(patterns) == 1 and patterns[0].title == "p1"

    def test_search_by_channel(self, tmp_path):
        from sovereign_agent.stewardship.atoms import (
            Atom, AtomKind, AtomStore,
        )
        store = AtomStore(tmp_path / "atoms.ndjson")
        store.append(Atom(title="a", claim="", channels=["back-pain"],
                            evidence_refs=["x", "y"]))
        store.append(Atom(title="b", claim="", channels=["identity"],
                            evidence_refs=["x", "y"]))
        result = store.search(channel="back-pain")
        assert len(result) == 1 and result[0].title == "a"


# ─── Provenance loading ────────────────────────────────────────────────────


class TestProvenanceLoading:

    def test_load_empty(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import load_provenance
        # No file → empty list, no raise
        result = load_provenance(path=tmp_path / "missing.ndjson")
        assert result == []

    def test_load_parses_valid_lines(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import load_provenance
        path = tmp_path / "interpretations.ndjson"
        records = [
            {"ts": "2026-05-17T10:00:00", "text": "hello",
             "understanding": "greeting", "reasoning": "g",
             "save_to": ["context"], "commands": [],
             "authority_tier": 0, "uncertain_about": "",
             "intent_kind": "Conversation"},
            {"ts": "2026-05-17T10:01:00", "text": "back hurts",
             "understanding": "pain", "reasoning": "p",
             "save_to": ["emotions", "back-pain"], "commands": [],
             "authority_tier": 0, "uncertain_about": "",
             "intent_kind": "Conversation"},
        ]
        with path.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        loaded = load_provenance(path=path)
        assert len(loaded) == 2
        assert loaded[1].save_to == ["emotions", "back-pain"]

    def test_load_skips_malformed(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import load_provenance
        path = tmp_path / "interpretations.ndjson"
        with path.open("w") as f:
            f.write(json.dumps({"ts": "x", "text": "ok",
                                 "save_to": []}) + "\n")
            f.write("not valid json\n")
            f.write(json.dumps({"ts": "y", "text": "ok2",
                                 "save_to": []}) + "\n")
        loaded = load_provenance(path=path)
        assert len(loaded) == 2

    def test_load_tail_n(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import load_provenance
        path = tmp_path / "interpretations.ndjson"
        with path.open("w") as f:
            for i in range(50):
                f.write(json.dumps({"ts": f"t{i}", "text": f"m{i}",
                                     "save_to": []}) + "\n")
        loaded = load_provenance(path=path, tail_n=10)
        assert len(loaded) == 10
        assert loaded[0].text == "m40"
        assert loaded[-1].text == "m49"

    def test_entry_id_is_stable(self):
        """Same ts + text prefix should produce the same entry_id."""
        from sovereign_agent.stewardship.consolidate import ProvenanceEntry
        p1 = ProvenanceEntry(ts="2026-05-17T10:00:00", text="hello world")
        p2 = ProvenanceEntry(ts="2026-05-17T10:00:00", text="hello world")
        assert p1.entry_id == p2.entry_id


# ─── Clustering ────────────────────────────────────────────────────────────


class TestClustering:

    def test_exact_channel_set_match_clusters(self):
        from sovereign_agent.stewardship.consolidate import (
            ProvenanceEntry, cluster_by_channel,
        )
        entries = [
            ProvenanceEntry(ts="t1", text="a", save_to=["back-pain", "emotions"]),
            ProvenanceEntry(ts="t2", text="b", save_to=["back-pain", "emotions"]),
            ProvenanceEntry(ts="t3", text="c", save_to=["back-pain", "emotions"]),
            ProvenanceEntry(ts="t4", text="d", save_to=["identity"]),
        ]
        clusters = cluster_by_channel(entries, min_cluster_size=3)
        # Only the back-pain+emotions cluster meets size=3
        assert len(clusters) == 1
        key = frozenset({"back-pain", "emotions"})
        assert key in clusters
        assert len(clusters[key]) == 3

    def test_singletons_dropped(self):
        from sovereign_agent.stewardship.consolidate import (
            ProvenanceEntry, cluster_by_channel,
        )
        entries = [
            ProvenanceEntry(ts=f"t{i}", text=f"m{i}",
                             save_to=[f"channel-{i}"])
            for i in range(10)
        ]
        clusters = cluster_by_channel(entries, min_cluster_size=2)
        assert len(clusters) == 0

    def test_empty_channels_skipped(self):
        from sovereign_agent.stewardship.consolidate import (
            ProvenanceEntry, cluster_by_channel,
        )
        entries = [
            ProvenanceEntry(ts="t1", text="a", save_to=[]),
            ProvenanceEntry(ts="t2", text="b", save_to=[]),
            ProvenanceEntry(ts="t3", text="c", save_to=[]),
        ]
        clusters = cluster_by_channel(entries, min_cluster_size=2)
        assert len(clusters) == 0

    def test_different_orderings_are_same_cluster(self):
        """save_to=[a, b] and save_to=[b, a] are the same cluster."""
        from sovereign_agent.stewardship.consolidate import (
            ProvenanceEntry, cluster_by_channel,
        )
        entries = [
            ProvenanceEntry(ts="t1", text="a", save_to=["x", "y"]),
            ProvenanceEntry(ts="t2", text="b", save_to=["y", "x"]),
            ProvenanceEntry(ts="t3", text="c", save_to=["x", "y"]),
        ]
        clusters = cluster_by_channel(entries, min_cluster_size=3)
        assert len(clusters) == 1


# ─── Consolidation operator ────────────────────────────────────────────────


def _mock_consolidation_client(atoms_response):
    """Build a mock LLM client that returns one fixed atoms response."""
    client = MagicMock()
    client.chat = AsyncMock(return_value={
        "message": {"role": "assistant",
                     "content": json.dumps(atoms_response)}
    })
    return client


class TestConsolidate:

    def test_offline_is_no_op(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import consolidate
        from sovereign_agent.stewardship.atoms import AtomStore

        # Write some provenance
        path = tmp_path / "interpretations.ndjson"
        for i in range(5):
            with path.open("a") as f:
                f.write(json.dumps({
                    "ts": f"t{i}", "text": f"m{i}",
                    "save_to": ["x", "y"],
                    "understanding": "", "reasoning": "",
                    "commands": [], "authority_tier": 0,
                    "uncertain_about": "", "intent_kind": "Conversation",
                }) + "\n")

        store = AtomStore(tmp_path / "atoms.ndjson")
        summary = asyncio.run(consolidate(
            ollama_client=None,
            tail_n=100,
            min_cluster_size=2,
            atom_store=store,
            provenance_path=path,
        ))

        assert summary["entries_read"] == 5
        assert summary["clusters_found"] == 1
        assert summary["clusters_consolidated"] == 0
        assert summary["skipped_offline"] == 1
        assert summary["atoms_saved"] == 0

    def test_llm_proposes_valid_atom(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import (
            consolidate, load_provenance,
        )
        from sovereign_agent.stewardship.atoms import AtomStore

        path = tmp_path / "interpretations.ndjson"
        for i in range(3):
            with path.open("a") as f:
                f.write(json.dumps({
                    "ts": f"2026-05-17T10:0{i}:00",
                    "text": f"my back hurts today {i}",
                    "save_to": ["back-pain", "emotions"],
                    "understanding": "pain check-in",
                    "reasoning": "body content",
                    "commands": [], "authority_tier": 0,
                    "uncertain_about": "", "intent_kind": "Conversation",
                }) + "\n")

        entries = load_provenance(path=path)
        entry_ids = [e.entry_id for e in entries]

        client = _mock_consolidation_client({
            "atoms": [{
                "kind": "pattern",
                "title": "kevin checks in about back pain regularly",
                "claim": "Kevin sends body+emotions messages mentioning back pain",
                "confidence": 0.8,
                "evidence_entry_ids": entry_ids,
                "tags": ["schedule"],
            }]
        })

        store = AtomStore(tmp_path / "atoms.ndjson")
        summary = asyncio.run(consolidate(
            ollama_client=client,
            tail_n=100,
            min_cluster_size=3,
            atom_store=store,
            provenance_path=path,
        ))

        assert summary["atoms_saved"] == 1
        atoms = store.active()
        assert len(atoms) == 1
        assert atoms[0].kind.value == "pattern"
        assert "back-pain" in atoms[0].channels
        assert len(atoms[0].evidence_refs) == 3

    def test_atom_with_single_evidence_ref_is_dropped(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import (
            consolidate, load_provenance,
        )
        from sovereign_agent.stewardship.atoms import AtomStore

        path = tmp_path / "interpretations.ndjson"
        for i in range(3):
            with path.open("a") as f:
                f.write(json.dumps({
                    "ts": f"2026-05-17T10:0{i}:00",
                    "text": f"msg {i}",
                    "save_to": ["x", "y"],
                    "understanding": "", "reasoning": "",
                    "commands": [], "authority_tier": 0,
                    "uncertain_about": "", "intent_kind": "Conversation",
                }) + "\n")

        entries = load_provenance(path=path)

        client = _mock_consolidation_client({
            "atoms": [{
                "kind": "fact",
                "title": "bad atom",
                "claim": "x",
                "confidence": 0.9,
                "evidence_entry_ids": [entries[0].entry_id],
            }]
        })
        store = AtomStore(tmp_path / "atoms.ndjson")
        summary = asyncio.run(consolidate(
            ollama_client=client,
            tail_n=100,
            min_cluster_size=3,
            atom_store=store,
            provenance_path=path,
        ))
        assert summary["atoms_saved"] == 0

    def test_atom_with_fake_evidence_id_is_dropped(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import consolidate
        from sovereign_agent.stewardship.atoms import AtomStore

        path = tmp_path / "interpretations.ndjson"
        for i in range(3):
            with path.open("a") as f:
                f.write(json.dumps({
                    "ts": f"t{i}", "text": f"m{i}",
                    "save_to": ["x", "y"],
                    "understanding": "", "reasoning": "",
                    "commands": [], "authority_tier": 0,
                    "uncertain_about": "", "intent_kind": "Conversation",
                }) + "\n")

        client = _mock_consolidation_client({
            "atoms": [{
                "kind": "fact",
                "title": "hallucinated",
                "claim": "x",
                "confidence": 0.9,
                "evidence_entry_ids": ["fake-id-1", "fake-id-2"],
            }]
        })
        store = AtomStore(tmp_path / "atoms.ndjson")
        summary = asyncio.run(consolidate(
            ollama_client=client,
            tail_n=100,
            min_cluster_size=3,
            atom_store=store,
            provenance_path=path,
        ))
        assert summary["atoms_saved"] == 0

    def test_llm_returning_malformed_response_handled(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import consolidate
        from sovereign_agent.stewardship.atoms import AtomStore

        path = tmp_path / "interpretations.ndjson"
        for i in range(3):
            with path.open("a") as f:
                f.write(json.dumps({
                    "ts": f"t{i}", "text": f"m{i}",
                    "save_to": ["x", "y"],
                    "understanding": "", "reasoning": "",
                    "commands": [], "authority_tier": 0,
                    "uncertain_about": "", "intent_kind": "Conversation",
                }) + "\n")

        client = MagicMock()
        client.chat = AsyncMock(return_value={
            "message": {"role": "assistant", "content": "not json"}
        })
        store = AtomStore(tmp_path / "atoms.ndjson")
        summary = asyncio.run(consolidate(
            ollama_client=client,
            tail_n=100,
            min_cluster_size=3,
            atom_store=store,
            provenance_path=path,
        ))
        assert summary["atoms_saved"] == 0
        assert summary["clusters_consolidated"] == 1


# ─── Doctrine ──────────────────────────────────────────────────────────────


class TestPalimpsestDoctrine:
    """The system never silently destroys what came before."""

    def test_atoms_log_is_append_only(self, tmp_path):
        from sovereign_agent.stewardship.atoms import AtomStore
        store = AtomStore(tmp_path / "atoms.ndjson")
        assert not hasattr(store, "delete")
        assert not hasattr(store, "remove")
        assert not hasattr(store, "clear")
        assert not hasattr(store, "truncate")

    def test_consolidate_does_not_delete_provenance(self, tmp_path):
        from sovereign_agent.stewardship.consolidate import consolidate
        from sovereign_agent.stewardship.atoms import AtomStore

        path = tmp_path / "interpretations.ndjson"
        original_content = ""
        for i in range(3):
            entry = json.dumps({
                "ts": f"t{i}", "text": f"m{i}",
                "save_to": ["x", "y"],
                "understanding": "", "reasoning": "",
                "commands": [], "authority_tier": 0,
                "uncertain_about": "", "intent_kind": "Conversation",
            }) + "\n"
            with path.open("a") as f:
                f.write(entry)
            original_content += entry

        store = AtomStore(tmp_path / "atoms.ndjson")
        asyncio.run(consolidate(
            ollama_client=None,
            tail_n=100,
            min_cluster_size=3,
            atom_store=store,
            provenance_path=path,
        ))

        assert path.read_text() == original_content
