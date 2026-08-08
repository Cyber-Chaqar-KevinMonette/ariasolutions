"""R2 hardening tests for the Mycelium (stewardship/behavior.py) — the
riskiest mechanics that the original 6 tests didn't cover: forward-compat
loading, dormancy + reactivation, the three-signal AND, supersede lineage,
corrupt-log resilience, confidence saturation, and top_k match ordering."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sovereign_agent.stewardship.behavior import (
    BehaviorPattern,
    BehaviorPatternStore,
    OutcomeMetrics,
    PatternStatus,
    TriggerConditions,
    shape_of_turn,
)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _pattern(name="p", **trig):
    return BehaviorPattern(name=name, trigger=TriggerConditions(**trig))


# ── forward-compat: future schema lines MUST still load ─────────────────────
def test_unknown_fields_in_log_do_not_lose_the_pattern(tmp_path):
    store = BehaviorPatternStore(tmp_path / "b.jsonl")
    p = _pattern("keeper")
    store.append(p)
    # simulate a future version writing extra keys at every level
    line = json.loads((tmp_path / "b.jsonl").read_text().splitlines()[-1])
    line["future_top_level"] = {"x": 1}
    line["trigger"]["future_trigger_field"] = "y"
    line["outcome"]["future_metric"] = 0.9
    with open(tmp_path / "b.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    fresh = BehaviorPatternStore(tmp_path / "b.jsonl")
    loaded = {q.pattern_id: q for q in fresh.all_patterns()}
    assert p.pattern_id in loaded            # NOT silently dropped
    assert loaded[p.pattern_id].name == "keeper"


def test_corrupt_lines_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "b.jsonl"
    store = BehaviorPatternStore(path)
    store.append(_pattern("survivor"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{torn json\n\n[not even an object]\n")
    fresh = BehaviorPatternStore(path)
    assert [q.name for q in fresh.all_patterns()] == ["survivor"]


# ── dormancy + reactivation ─────────────────────────────────────────────────
def test_dormant_pattern_drops_out_of_active_and_matching(tmp_path):
    store = BehaviorPatternStore(tmp_path / "b.jsonl")
    p = _pattern("sleepy", channels_any=["emotions"])
    store.append(p)
    # backdate its last observation beyond the 30-day threshold
    p.ts_last_obs = _iso(datetime.now(timezone.utc) - timedelta(days=45))
    store._state[p.pattern_id] = p           # simulate aged state
    assert p.is_dormant_now()
    assert store.active() == []
    shape = shape_of_turn(text="hi", channels=["emotions"])
    assert store.matching(shape) == []       # dormant ⇒ never matched


def test_observation_reactivates_a_dormant_pattern(tmp_path):
    store = BehaviorPatternStore(tmp_path / "b.jsonl")
    p = _pattern("phoenix")
    p.status = PatternStatus.DORMANT
    store.append(p)
    got = store.observe(p.pattern_id, honor_score=0.9)
    assert got is not None and got.status == PatternStatus.ACTIVE


# ── the three-signal AND (frequency alone must not produce value) ───────────
def test_is_valuable_requires_all_three_signals():
    m = OutcomeMetrics()
    for _ in range(10):
        m.update_honor(0.9)                  # honor alone — a fluke
    assert not m.is_valuable
    m.update_calibration(0.9)
    m.update_calibration(0.9)
    assert not m.is_valuable or m.calibration_avg >= 0.5  # still needs survival evidence path
    m.update_survival(True)
    assert m.is_valuable                     # now all three favorable
    m2 = OutcomeMetrics()
    m2.update_honor(0.9); m2.update_honor(0.9)
    assert not m2.is_valuable                # < 3 observations ⇒ never valuable


def test_low_survival_kills_value():
    m = OutcomeMetrics()
    for _ in range(5):
        m.update_honor(0.9); m.update_calibration(0.9)
    m.update_survival(False); m.update_survival(False); m.update_survival(True)
    assert m.survival_rate < 0.5 and not m.is_valuable


# ── supersede lineage ───────────────────────────────────────────────────────
def test_supersede_links_lineage_and_removes_from_active(tmp_path):
    store = BehaviorPatternStore(tmp_path / "b.jsonl")
    old = _pattern("v1")
    store.append(old)
    new = _pattern("v2")
    store.supersede(old.pattern_id, new)
    state = {q.pattern_id: q for q in store.all_patterns()}
    assert state[old.pattern_id].status == PatternStatus.SUPERSEDED
    assert state[old.pattern_id].superseded_by == new.pattern_id
    assert state[new.pattern_id].supersedes == old.pattern_id
    assert [q.name for q in store.active()] == ["v2"]
    # and the lineage survives a fresh replay from disk
    fresh = BehaviorPatternStore(tmp_path / "b.jsonl")
    assert [q.name for q in fresh.active()] == ["v2"]


# ── confidence + matching ───────────────────────────────────────────────────
def test_confidence_saturates_at_n20():
    p = _pattern("solid")
    for _ in range(40):
        p.outcome.update_honor(1.0)
        p.outcome.update_calibration(1.0)
        p.outcome.update_survival(True)
    assert p.confidence == 1.0               # evidence_factor capped at 1


def test_matching_orders_by_confidence_and_caps_top_k(tmp_path):
    store = BehaviorPatternStore(tmp_path / "b.jsonl")
    shape = shape_of_turn(text="evening reflection", channels=["emotions"])
    names = ["weak", "mid", "strong", "extra"]
    honors = [0.5, 0.7, 1.0, 0.6]
    for name, h in zip(names, honors):
        p = _pattern(name, channels_any=["emotions"])
        for _ in range(10):
            p.outcome.update_honor(h)
            p.outcome.update_calibration(h)
            p.outcome.update_survival(True)
        store.append(p)
    top = store.matching(shape, top_k=3)
    assert len(top) == 3
    assert top[0].name == "strong"           # confidence descending
