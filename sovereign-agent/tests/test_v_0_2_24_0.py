"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_24_0.py — the Self-Perception Layer                           ║
║                                                                           ║
║  Tests the new L3 reframed: emergent self-perceived patterns from        ║
║  honor + calibration + survival signals.                                  ║
║                                                                           ║
║  Invariants:                                                              ║
║    1. Trigger matching is pure, deterministic, and bounded-cost          ║
║    2. OutcomeMetrics correctly identifies "valuable" patterns            ║
║    3. The pattern log is append-only; supersession preserves history    ║
║    4. Discovery is no-op offline; LLM proposals are filtered            ║
║    5. Patterns proposed without valid evidence (< 3 refs) are dropped   ║
║    6. Dormancy is reversible — a new observation re-activates           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── Trigger matching ─────────────────────────────────────────────────────


class TestTriggerMatching:

    def test_channels_any_matches_when_any_present(self):
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions(channels_any=["emotions", "back-pain"])
        shape = shape_of_turn(channels=["emotions", "context"])
        assert trigger.matches(shape)

    def test_channels_any_fails_when_none_present(self):
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions(channels_any=["humor", "play"])
        shape = shape_of_turn(channels=["emotions"])
        assert not trigger.matches(shape)

    def test_channels_all_requires_every_one(self):
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions(channels_all=["identity", "intention"])
        shape = shape_of_turn(channels=["identity"])
        assert not trigger.matches(shape)
        shape2 = shape_of_turn(channels=["identity", "intention", "emotions"])
        assert trigger.matches(shape2)

    def test_authority_tier_max(self):
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions(authority_tier_max=1)
        assert trigger.matches(shape_of_turn(authority_tier=0))
        assert trigger.matches(shape_of_turn(authority_tier=1))
        assert not trigger.matches(shape_of_turn(authority_tier=2))

    def test_text_contains_any(self):
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions(text_contains_any=["love", "joy"])
        assert trigger.matches(shape_of_turn(text="with love and care"))
        assert trigger.matches(shape_of_turn(text="JOY in the morning"))
        assert not trigger.matches(shape_of_turn(text="just data"))

    def test_empty_trigger_matches_everything(self):
        """An empty trigger trivially matches. The discovery operator
        is responsible for rejecting empty triggers — this is the
        trigger matcher's correct behavior (no constraints = match)."""
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions()
        assert trigger.matches(shape_of_turn(text="anything"))

    def test_multiple_constraints_AND_together(self):
        from sovereign_agent.stewardship.behavior import (
            TriggerConditions, shape_of_turn,
        )
        trigger = TriggerConditions(
            channels_any=["emotions"],
            authority_tier_max=0,
            text_contains_any=["pain"],
        )
        # All three satisfied
        assert trigger.matches(shape_of_turn(
            text="my back is in pain",
            channels=["emotions", "back-pain"],
            authority_tier=0,
        ))
        # Tier fails
        assert not trigger.matches(shape_of_turn(
            text="pain check",
            channels=["emotions"],
            authority_tier=2,
        ))
        # Channels fail
        assert not trigger.matches(shape_of_turn(
            text="pain check",
            channels=["context"],
            authority_tier=0,
        ))


# ─── OutcomeMetrics ────────────────────────────────────────────────────────


class TestOutcomeMetrics:

    def test_initial_metrics_not_valuable(self):
        from sovereign_agent.stewardship.behavior import OutcomeMetrics
        m = OutcomeMetrics()
        assert not m.is_valuable

    def test_valuable_requires_three_observations(self):
        from sovereign_agent.stewardship.behavior import OutcomeMetrics
        m = OutcomeMetrics()
        m.update_honor(0.8)
        m.update_calibration(0.8)
        m.update_survival(True)
        # n=1 — not enough evidence
        assert not m.is_valuable
        m.update_honor(0.8)
        m.update_calibration(0.8)
        m.update_survival(True)
        m.update_honor(0.8)
        m.update_calibration(0.8)
        m.update_survival(True)
        # n=3 with all signals high
        assert m.is_valuable

    def test_one_low_signal_invalidates(self):
        from sovereign_agent.stewardship.behavior import OutcomeMetrics
        m = OutcomeMetrics()
        for _ in range(5):
            m.update_honor(0.9)
            m.update_calibration(0.3)   # low calibration
            m.update_survival(True)
        assert not m.is_valuable

    def test_survival_defaults_neutral_positive(self):
        """Absent survival evidence, assume neutral. This lets new
        patterns become 'valuable' before their atoms have aged
        enough to be tested for survival."""
        from sovereign_agent.stewardship.behavior import OutcomeMetrics
        m = OutcomeMetrics()
        for _ in range(3):
            m.update_honor(0.8)
            m.update_calibration(0.7)
        # No survival updates → survival_rate == 1.0 (neutral default)
        assert m.is_valuable


# ─── BehaviorPattern lifecycle ─────────────────────────────────────────────


class TestPatternLifecycle:

    def test_pattern_dormancy(self):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, PatternStatus,
        )
        # Backdate observation to 60 days ago
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        p = BehaviorPattern(
            name="old", description="ancient",
            ts_last_obs=old_ts,
        )
        assert p.is_dormant_now(threshold_days=30)
        # Recent observation
        new_ts = datetime.now(timezone.utc).isoformat()
        p2 = BehaviorPattern(ts_last_obs=new_ts)
        assert not p2.is_dormant_now(threshold_days=30)

    def test_status_coerced_from_string(self):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, PatternStatus,
        )
        # JSON round-trip produces status as string
        p = BehaviorPattern(status="dormant")  # type: ignore[arg-type]
        assert p.status == PatternStatus.DORMANT

    def test_nested_dataclasses_coerced(self):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, TriggerConditions, OutcomeMetrics,
        )
        # Simulate JSON round-trip where nested dataclasses come back as dicts
        p = BehaviorPattern(
            trigger={"channels_any": ["x"]},  # type: ignore[arg-type]
            outcome={"honor_n": 5, "honor_sum": 4.0,  # type: ignore[arg-type]
                      "calibration_n": 0, "calibration_sum": 0,
                      "survival_yes": 0, "survival_total": 0},
        )
        assert isinstance(p.trigger, TriggerConditions)
        assert isinstance(p.outcome, OutcomeMetrics)
        assert p.trigger.channels_any == ["x"]


# ─── BehaviorPatternStore ──────────────────────────────────────────────────


class TestPatternStore:

    def test_append_and_active(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, TriggerConditions,
        )
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        p1 = BehaviorPattern(
            name="p1", description="first",
            trigger=TriggerConditions(channels_any=["x"]),
        )
        p2 = BehaviorPattern(
            name="p2", description="second",
            trigger=TriggerConditions(channels_any=["y"]),
        )
        store.append(p1)
        store.append(p2)
        active = store.active()
        names = {p.name for p in active}
        assert names == {"p1", "p2"}

    def test_observe_updates_outcome(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, TriggerConditions,
        )
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        p = BehaviorPattern(name="test", description="t",
                              trigger=TriggerConditions(channels_any=["x"]))
        store.append(p)
        # Record an observation
        updated = store.observe(
            p.pattern_id,
            honor_score=0.8,
            calibration_score=0.9,
            evidence_ref="entry-1",
        )
        assert updated is not None
        assert updated.outcome.honor_avg == 0.8
        assert updated.outcome.calibration_avg == 0.9
        assert "entry-1" in updated.evidence_refs

    def test_supersession_preserves_log(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, PatternStatus,
        )
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        old = BehaviorPattern(name="old", description="x")
        store.append(old)
        new = BehaviorPattern(name="new", description="y")
        store.supersede(old.pattern_id, new)
        # Active: only new
        active = store.active()
        assert len(active) == 1
        assert active[0].pattern_id == new.pattern_id
        # Raw log has the old + status update for old + new = 3 lines min
        store.invalidate()
        all_states = list(store.all_patterns())
        # Replay yields current state of each id (2 ids)
        assert len(all_states) == 2

    def test_matching_returns_top_k_by_confidence(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, OutcomeMetrics,
            TriggerConditions, shape_of_turn,
        )
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        # Three patterns all matching, different confidences
        for i, score in enumerate([0.9, 0.5, 0.7]):
            outcome = OutcomeMetrics()
            for _ in range(20):
                outcome.update_honor(score)
                outcome.update_calibration(score)
            p = BehaviorPattern(
                name=f"p{i}",
                description=f"#{i}",
                trigger=TriggerConditions(channels_any=["x"]),
                outcome=outcome,
            )
            store.append(p)
        matches = store.matching(
            shape_of_turn(channels=["x"]),
            top_k=2,
        )
        # Sorted by confidence; top should be the 0.9 one
        assert len(matches) == 2
        assert matches[0].name == "p0"   # highest confidence
        assert matches[1].name == "p2"   # second

    def test_dormancy_filters_active(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, TriggerConditions,
        )
        # Construct a pattern that's already dormant by its timestamp.
        # We do NOT call store.append() because append() updates
        # ts_last_obs to NOW — appropriate at write time, but it would
        # invalidate the dormancy timestamp we're testing.
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(
            timespec="seconds"
        )
        stale = BehaviorPattern(
            name="stale", description="y",
            trigger=TriggerConditions(channels_any=["b"]),
            ts_last_obs=old_ts,
        )
        assert stale.is_dormant_now(threshold_days=30)
        # A pattern observed today is not dormant
        fresh = BehaviorPattern(name="fresh", description="x")
        assert not fresh.is_dormant_now(threshold_days=30)

    def test_observation_reactivates_dormant(self, tmp_path):
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, PatternStatus,
            TriggerConditions,
        )
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        p = BehaviorPattern(
            name="sleepy", description="x",
            trigger=TriggerConditions(channels_any=["x"]),
            status=PatternStatus.DORMANT,
        )
        store.append(p)
        updated = store.observe(p.pattern_id, honor_score=0.7)
        assert updated.status == PatternStatus.ACTIVE


# ─── Discovery operator ────────────────────────────────────────────────────


def _mock_discovery_client(patterns_response):
    client = MagicMock()
    client.chat = AsyncMock(return_value={
        "message": {"role": "assistant",
                     "content": json.dumps(patterns_response)}
    })
    return client


class TestDiscovery:

    def _write_provenance(self, tmp_path, count: int):
        path = tmp_path / "interpretations.ndjson"
        for i in range(count):
            with path.open("a") as f:
                f.write(json.dumps({
                    "ts": f"2026-05-17T20:0{i % 6}:00",
                    "text": f"my back hurts {i}",
                    "save_to": ["back-pain", "emotions"],
                    "understanding": "pain check",
                    "reasoning": "body content",
                    "commands": [], "authority_tier": 0,
                    "uncertain_about": "", "intent_kind": "Conversation",
                }) + "\n")
        return path

    def test_offline_is_no_op(self, tmp_path):
        from sovereign_agent.stewardship.discovery import discover_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        path = self._write_provenance(tmp_path, 5)
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        summary = asyncio.run(discover_patterns(
            ollama_client=None,
            pattern_store=store,
            provenance_path=path,
            honor_path=tmp_path / "no-honor.jsonl",
        ))
        assert summary["skipped_offline"] is True
        assert summary["patterns_saved"] == 0

    def test_valid_pattern_proposal_saved(self, tmp_path):
        from sovereign_agent.stewardship.discovery import discover_patterns
        from sovereign_agent.stewardship.consolidate import load_provenance
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        path = self._write_provenance(tmp_path, 5)
        entries = load_provenance(path=path)
        entry_ids = [e.entry_id for e in entries[:3]]

        client = _mock_discovery_client({
            "patterns": [{
                "name": "evening-pain-checkin",
                "description": "When Kevin sends back-pain content, I respond briefly",
                "trigger": {
                    "channels_any": ["back-pain", "emotions"],
                    "authority_tier_max": 0,
                },
                "action_shape": "save to body+emotions, respond briefly",
                "evidence_entry_ids": entry_ids,
                "tags": ["evening", "self-care"],
            }]
        })

        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        summary = asyncio.run(discover_patterns(
            ollama_client=client,
            pattern_store=store,
            provenance_path=path,
            honor_path=tmp_path / "no-honor.jsonl",
        ))
        assert summary["patterns_saved"] == 1
        patterns = store.active()
        assert len(patterns) == 1
        assert patterns[0].name == "evening-pain-checkin"
        assert "back-pain" in patterns[0].trigger.channels_any

    def test_empty_trigger_pattern_dropped(self, tmp_path):
        """A pattern with no constraint would match everything — drop it."""
        from sovereign_agent.stewardship.discovery import discover_patterns
        from sovereign_agent.stewardship.consolidate import load_provenance
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        path = self._write_provenance(tmp_path, 5)
        entries = load_provenance(path=path)
        entry_ids = [e.entry_id for e in entries[:3]]

        client = _mock_discovery_client({
            "patterns": [{
                "name": "empty-trigger",
                "description": "matches anything",
                "trigger": {},   # empty!
                "action_shape": "x",
                "evidence_entry_ids": entry_ids,
            }]
        })

        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        summary = asyncio.run(discover_patterns(
            ollama_client=client,
            pattern_store=store,
            provenance_path=path,
            honor_path=tmp_path / "no-honor.jsonl",
        ))
        assert summary["patterns_saved"] == 0

    def test_insufficient_evidence_dropped(self, tmp_path):
        """< 3 valid evidence refs → drop."""
        from sovereign_agent.stewardship.discovery import discover_patterns
        from sovereign_agent.stewardship.consolidate import load_provenance
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        path = self._write_provenance(tmp_path, 5)
        entries = load_provenance(path=path)

        client = _mock_discovery_client({
            "patterns": [{
                "name": "thin-evidence",
                "description": "only two examples",
                "trigger": {"channels_any": ["x"]},
                "action_shape": "x",
                "evidence_entry_ids": [entries[0].entry_id, entries[1].entry_id],
            }]
        })

        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        summary = asyncio.run(discover_patterns(
            ollama_client=client,
            pattern_store=store,
            provenance_path=path,
            honor_path=tmp_path / "no-honor.jsonl",
        ))
        assert summary["patterns_saved"] == 0

    def test_hallucinated_evidence_dropped(self, tmp_path):
        from sovereign_agent.stewardship.discovery import discover_patterns
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        path = self._write_provenance(tmp_path, 5)

        client = _mock_discovery_client({
            "patterns": [{
                "name": "fake-evidence",
                "description": "from nowhere",
                "trigger": {"channels_any": ["x"]},
                "action_shape": "x",
                "evidence_entry_ids": ["fake1", "fake2", "fake3"],
            }]
        })

        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        summary = asyncio.run(discover_patterns(
            ollama_client=client,
            pattern_store=store,
            provenance_path=path,
            honor_path=tmp_path / "no-honor.jsonl",
        ))
        assert summary["patterns_saved"] == 0

    def test_duplicate_name_not_saved_twice(self, tmp_path):
        from sovereign_agent.stewardship.discovery import discover_patterns
        from sovereign_agent.stewardship.consolidate import load_provenance
        from sovereign_agent.stewardship.behavior import (
            BehaviorPattern, BehaviorPatternStore, TriggerConditions,
        )
        path = self._write_provenance(tmp_path, 5)
        entries = load_provenance(path=path)
        entry_ids = [e.entry_id for e in entries[:3]]

        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        # Pre-existing pattern with the same name
        existing = BehaviorPattern(
            name="evening-pain-checkin",
            description="already here",
            trigger=TriggerConditions(channels_any=["back-pain"]),
        )
        store.append(existing)

        client = _mock_discovery_client({
            "patterns": [{
                "name": "evening-pain-checkin",   # duplicate
                "description": "new version",
                "trigger": {"channels_any": ["back-pain"]},
                "action_shape": "x",
                "evidence_entry_ids": entry_ids,
            }]
        })

        summary = asyncio.run(discover_patterns(
            ollama_client=client,
            pattern_store=store,
            provenance_path=path,
            honor_path=tmp_path / "no-honor.jsonl",
        ))
        assert summary["patterns_saved"] == 0   # duplicate dropped
        # Only one pattern with that name
        named = [p for p in store.active() if p.name == "evening-pain-checkin"]
        assert len(named) == 1


# ─── Doctrine ──────────────────────────────────────────────────────────────


class TestPalimpsestDoctrine:

    def test_pattern_store_is_append_only(self, tmp_path):
        from sovereign_agent.stewardship.behavior import BehaviorPatternStore
        store = BehaviorPatternStore(tmp_path / "patterns.ndjson")
        assert not hasattr(store, "delete")
        assert not hasattr(store, "remove")
        assert not hasattr(store, "clear")
        assert not hasattr(store, "truncate")

    def test_valuable_requires_all_three_signals(self):
        """The 'valuable' criterion ANDs three signals. This is the
        load-bearing claim of the whole system."""
        from sovereign_agent.stewardship.behavior import OutcomeMetrics
        m = OutcomeMetrics()
        for _ in range(5):
            m.update_honor(0.9)
            m.update_calibration(0.9)
            m.update_survival(True)
        assert m.is_valuable

        # Even with high frequency, low honor invalidates
        m2 = OutcomeMetrics()
        for _ in range(100):
            m2.update_honor(0.2)        # low
            m2.update_calibration(0.9)
            m2.update_survival(True)
        assert not m2.is_valuable

        # High honor, low calibration invalidates
        m3 = OutcomeMetrics()
        for _ in range(10):
            m3.update_honor(0.9)
            m3.update_calibration(0.2)  # low
            m3.update_survival(True)
        assert not m3.is_valuable
