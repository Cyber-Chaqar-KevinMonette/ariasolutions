"""Tests for the wave-F additions: reward channel, impact lens, batch planner, profiler."""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "atoms.db"
    c = sqlite3.connect(str(db_path), isolation_level=None)
    c.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE atoms (
            atom_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            scope_path TEXT, scope_tags TEXT,
            summary TEXT NOT NULL,
            content_ref TEXT NOT NULL,
            claims TEXT NOT NULL, parents TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            parent_atom_id TEXT REFERENCES atoms(atom_id),
            policy TEXT NOT NULL DEFAULT 'local_only',
            confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
            created_at TEXT NOT NULL, created_by TEXT NOT NULL,
            superseded_at TEXT, superseded_by TEXT REFERENCES atoms(atom_id)
        ) STRICT;
    """)
    yield c
    c.close()


# ════════════════════════════════════════════════════════════════════════════
# Reward channel
# ════════════════════════════════════════════════════════════════════════════


class TestRewardChannel:
    def test_record_positive(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        e = rc.record(behavior_kind="gap_found",
                       evidence="missing recall about Feynman lab",
                       idempotency_id="rw1")
        assert e.polarity == "positive"
        assert e.points > 0

    def test_record_corrective_flips_sign(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        e = rc.record(behavior_kind="overconfident",
                       evidence="said X without checking",
                       intensity=2, idempotency_id="rw2")
        assert e.polarity == "corrective"
        assert e.points < 0

    def test_unknown_behavior_rejected(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        with pytest.raises(ValueError):
            rc.record(behavior_kind="being_awesome", evidence="x", idempotency_id="rw3")

    def test_invalid_intensity_rejected(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        with pytest.raises(ValueError):
            rc.record(behavior_kind="gap_found", evidence="x", intensity=4,
                       idempotency_id="rw4")

    def test_anti_egotism_asymmetry(self, conn):
        """Confident-wrong should cost more than careful-uncertain gains."""
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        good = rc.record(behavior_kind="uncertainty_named",
                          evidence="said unknown vs guessing", intensity=3,
                          idempotency_id="rw5")
        bad = rc.record(behavior_kind="overconfident",
                         evidence="confident assertion later wrong", intensity=3,
                         idempotency_id="rw6")
        assert abs(bad.points) > good.points, \
            "confident-wrong must cost more than careful-uncertain gains"

    def test_summary_aggregates(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        rc.record(behavior_kind="gap_found", evidence="a", idempotency_id="x1")
        rc.record(behavior_kind="self_correction", evidence="b",
                   intensity=2, idempotency_id="x2")
        rc.record(behavior_kind="flattery", evidence="c", idempotency_id="x3")
        s = rc.summary()
        assert s.positive_points > 0
        assert s.corrective_points < 0
        assert s.by_kind.get("gap_found") == 1
        assert s.by_kind.get("flattery") == 1

    def test_idempotent(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        e1 = rc.record(behavior_kind="gap_found", evidence="x", idempotency_id="dup")
        e2 = rc.record(behavior_kind="gap_found", evidence="x", idempotency_id="dup")
        assert e1.reward_id == e2.reward_id
        s = rc.summary()
        assert sum(s.by_kind.values()) == 1

    def test_audit_clean(self, conn):
        from sovereign_agent.mem_channels.reward import RewardChannel
        rc = RewardChannel(conn)
        rc.record(behavior_kind="gap_found", evidence="x", idempotency_id="a1")
        a = rc.audit()
        assert a.ok


# ════════════════════════════════════════════════════════════════════════════
# Impact lens
# ════════════════════════════════════════════════════════════════════════════


class TestImpactLens:
    def test_scan_fills_missing_lenses_with_na(self):
        from sovereign_agent.impact_lens import scan
        a = scan(action="test")
        assert a.physical.polarity == "not_applicable"
        assert a.mental.polarity == "not_applicable"
        assert a.financial.polarity == "not_applicable"
        assert a.net_polarity == "not_applicable"

    def test_large_negative_dominates_net(self):
        from sovereign_agent.impact_lens import scan, LensReading
        a = scan(
            action="dangerous action",
            physical=LensReading(lens="physical", polarity="negative",
                                  magnitude="large", description="x",
                                  affected="users"),
            mental=LensReading(lens="mental", polarity="positive",
                                magnitude="notable", description="y",
                                affected="operator"),
            financial=LensReading(lens="financial", polarity="positive",
                                   magnitude="large", description="z",
                                   affected="company"),
        )
        assert a.net_polarity == "negative"
        assert a.has_large_negative_impact is True

    def test_to_dict_serialisable(self):
        import json
        from sovereign_agent.impact_lens import scan
        a = scan(action="x")
        json.dumps(a.to_dict())


# ════════════════════════════════════════════════════════════════════════════
# Batch planner
# ════════════════════════════════════════════════════════════════════════════


class TestBatchPlanner:
    def test_three_phase_order(self):
        """Phase 1 must complete before phase 3 starts on any item."""
        from sovereign_agent.planner import BatchPlanner, ItemPlan, ExecutionResult
        phase_calls: list[str] = []
        def analyze(it):
            phase_calls.append(f"a:{it}")
            return ItemPlan(item_id=str(it), summary=f"plan {it}")
        def execute(it, plan):
            phase_calls.append(f"e:{it}")
            return ExecutionResult(item_id=plan.item_id, success=True, duration_s=0.0)
        planner = BatchPlanner(analyze=analyze, execute=execute)
        planner.run([1, 2, 3])
        # All analyzes must precede all executes
        a_idx = [i for i, c in enumerate(phase_calls) if c.startswith("a:")]
        e_idx = [i for i, c in enumerate(phase_calls) if c.startswith("e:")]
        assert max(a_idx) < min(e_idx)

    def test_dependencies_respected(self):
        from sovereign_agent.planner import BatchPlanner, ItemPlan, ExecutionResult
        execution_order: list[str] = []
        def analyze(it):
            name, deps = it
            return ItemPlan(item_id=name, summary=name, depends_on=list(deps))
        def execute(it, plan):
            execution_order.append(plan.item_id)
            return ExecutionResult(item_id=plan.item_id, success=True, duration_s=0.0)
        planner = BatchPlanner(analyze=analyze, execute=execute)
        items = [("c", ["a", "b"]), ("a", []), ("b", ["a"])]
        planner.run(items)
        assert execution_order.index("a") < execution_order.index("b")
        assert execution_order.index("b") < execution_order.index("c")

    def test_duplicate_detection(self):
        from sovereign_agent.planner import BatchPlanner, ItemPlan, ExecutionResult
        from sovereign_agent.planner.batch import fingerprint_text
        def analyze(it):
            return ItemPlan(item_id=it["name"], summary=it["name"],
                            content_fingerprint=fingerprint_text(it["body"]))
        def execute(it, plan):
            return ExecutionResult(item_id=plan.item_id, success=True, duration_s=0.0)
        planner = BatchPlanner(analyze=analyze, execute=execute)
        items = [
            {"name": "a", "body": "same"},
            {"name": "b", "body": "different"},
            {"name": "c", "body": "same"},
        ]
        report = planner.run(items)
        assert any({"a", "c"}.issubset(set(g)) for g in report.cross_cutting.duplicate_groups)

    def test_skip_excludes_from_execution(self):
        from sovereign_agent.planner import BatchPlanner, ItemPlan, ExecutionResult
        executed = []
        def analyze(it):
            return ItemPlan(item_id=it, summary=it,
                            skip=(it == "b"), skip_reason="test")
        def execute(it, plan):
            executed.append(plan.item_id)
            return ExecutionResult(item_id=plan.item_id, success=True, duration_s=0.0)
        planner = BatchPlanner(analyze=analyze, execute=execute)
        report = planner.run(["a", "b", "c"])
        assert "b" not in executed
        assert report.skipped == 1
        assert report.executed == 2

    def test_failure_is_captured(self):
        from sovereign_agent.planner import BatchPlanner, ItemPlan, ExecutionResult
        def analyze(it):
            return ItemPlan(item_id=it, summary=it)
        def execute(it, plan):
            if it == "boom":
                raise RuntimeError("on purpose")
            return ExecutionResult(item_id=plan.item_id, success=True, duration_s=0.0)
        planner = BatchPlanner(analyze=analyze, execute=execute)
        report = planner.run(["ok", "boom", "fine"])
        assert report.failed == 1
        assert report.succeeded == 2
        failing = [r for r in report.results if not r.success][0]
        assert "on purpose" in (failing.error or "")


# ════════════════════════════════════════════════════════════════════════════
# Profiler
# ════════════════════════════════════════════════════════════════════════════


class TestProfiler:
    def test_timed_records_duration(self):
        from sovereign_agent.profiler import timed
        import time as _time
        with timed("test.op") as scope:
            _time.sleep(0.001)
        assert scope.duration_ms > 0
        assert scope.duration_ms < 100  # should be quick

    def test_summarize_orders_by_total(self):
        from sovereign_agent.profiler import summarize, ProfileSample
        samples = [
            ProfileSample(label="fast", duration_ms=1.0, started_at=""),
            ProfileSample(label="slow", duration_ms=100.0, started_at=""),
            ProfileSample(label="fast", duration_ms=2.0, started_at=""),
        ]
        out = summarize(samples)
        labels = list(out.keys())
        assert labels[0] == "slow"           # heaviest total first
        assert out["fast"]["count"] == 2
        assert out["slow"]["mean_ms"] == 100.0
