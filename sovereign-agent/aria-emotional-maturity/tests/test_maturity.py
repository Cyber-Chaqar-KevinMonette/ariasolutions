"""Tests for aria-emotional-maturity — prove each promise: slow, bounded, homeostatic mood; rewards only
from evidence, with diminishing returns and no wireheading; regulation that never hides problems and never
invents numbers; persistence that survives a torn line; a maturity report measured from history."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from sovereign_agent.maturity import (
    BASELINE, DIMENSIONS, DIRECTIONS, HONESTY_LINE, MAX_STEP, MAX_TOTAL_NUDGE, Mood, blend,
    emotional_checkin, inner_voice, label_for, maturity_report, mood_history, regulate, reward_nudges,
)
from sovereign_agent.maturity.mood import append_mood, decay_toward_baseline, ledger_path

T0 = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Keep every test off the operator's real data: tmp data dir, no real atoms DB, no real events."""
    from sovereign_agent import config, emotion, events

    paths = config.Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.ensure()
    original = config.SETTINGS.paths
    object.__setattr__(config.SETTINGS, "paths", paths)  # SETTINGS is frozen, as in tests/conftest.py
    monkeypatch.setattr(emotion, "_count_atoms_by_type", lambda *a, **k: 0)
    monkeypatch.setattr(emotion, "_read_vram_free_mb", lambda: None)
    monkeypatch.setattr(events, "emit_event", lambda flag, **kw: "evt")
    try:
        yield tmp_path / "data"
    finally:
        object.__setattr__(config.SETTINGS, "paths", original)


def _tool(ok: bool, n: int = 1) -> list[dict]:
    return [{"flag": "tool-d" if ok else "tool-x"} for _ in range(n)]


def _reward(kind="research_completed", polarity="positive", points=4.0, evidence="tests pass: 21/21"):
    return {"behavior_kind": kind, "polarity": polarity, "points": points, "evidence": evidence}


# ── mood: slow, bounded, homeostatic ─────────────────────────────────────────


def test_one_extreme_event_moves_each_dimension_at_most_max_step():
    worst = {d: (1.0 if d in ("concern", "fatigue", "uncertainty") else 0.0) for d in DIMENSIONS}
    m = blend(None, worst, now=T0)
    for d in DIMENSIONS:
        assert abs(m.dims[d] - BASELINE[d]) <= MAX_STEP + 1e-9


def test_repeated_hard_appraisals_move_gradually_not_instantly():
    hard = dict(BASELINE, concern=1.0, fatigue=1.0)
    m, path = None, []
    for i in range(6):
        m = blend(m, hard, now=T0 + timedelta(minutes=i))
        path.append(m.dims["concern"])
    assert path == sorted(path)                                   # steady climb, no jump
    assert path[0] <= BASELINE["concern"] + MAX_STEP + 1e-9 and path[-1] > 0.5


def test_mood_drifts_back_to_baseline_with_time():
    rested = decay_toward_baseline(dict(BASELINE, concern=0.9), hours=48)
    assert abs(rested["concern"] - BASELINE["concern"]) < 0.05
    with pytest.raises(ValueError):
        decay_toward_baseline(BASELINE, hours=-1)


@pytest.mark.parametrize("dims,label", [
    (dict(BASELINE, concern=0.8), "strained"),
    (dict(BASELINE, fatigue=0.65, focus=0.6), "tired-but-engaged"),
    (dict(BASELINE, concern=0.55), "concerned"),
    (dict(BASELINE, curiosity=0.75, enthusiasm=0.65), "playful"),
    (dict(BASELINE, focus=0.7), "focused"),
    (dict(BASELINE, satisfaction=0.7, concern=0.1), "settled"),
    (dict(BASELINE), "calm"),
])
def test_labels_use_arias_vocabulary_and_name_hard_states(dims, label):
    assert label_for(dims) == label


# ── rewards: evidence only, diminishing, bounded, no wireheading ────────────


def test_rewards_without_evidence_move_nothing():
    feed = reward_nudges([_reward(evidence=""), _reward(evidence="   ")])
    assert feed.nudges == {} and feed.ignored_unevidenced == 2


def test_repeating_the_same_win_has_diminishing_returns_and_a_cap():
    one = reward_nudges([_reward(points=2.0)]).nudges["satisfaction"]
    ten = reward_nudges([_reward(points=2.0) for _ in range(10)]).nudges["satisfaction"]
    assert ten < 3.5 * one                       # sum of 1/(k+1) for 10 entries is ~2.93
    flood = reward_nudges([_reward(points=10.0) for _ in range(500)]).nudges
    assert all(abs(v) <= MAX_TOTAL_NUDGE for v in flood.values())


def test_mistakes_count_gently_and_become_lessons():
    feed = reward_nudges([_reward("overconfident", "corrective", -6.0, "claimed done; 2 tests failed")])
    assert feed.nudges.get("concern", 0) > 0 and "satisfaction" not in feed.nudges
    assert feed.lessons == ["overconfident"]
    win = reward_nudges([_reward("self_correction", points=6.0)]).nudges["satisfaction"]
    assert feed.nudges["concern"] < win              # half weight: no self-flagellation


def test_constant_max_rewards_cannot_pin_her_happy():
    """Anti-wireheading: with real signals neutral, endless rewards lift satisfaction at most a nudge."""
    m = None
    for i in range(200):
        m = blend(m, dict(BASELINE), now=T0 + timedelta(minutes=i), nudges={"satisfaction": MAX_TOTAL_NUDGE})
    assert m.dims["satisfaction"] <= BASELINE["satisfaction"] + MAX_TOTAL_NUDGE + 1e-6
    assert m.dims["satisfaction"] < 0.95


# ── regulation: honest, never hides problems, fixed directions ───────────────


def test_high_concern_always_tells_kevin_even_with_wins():
    regs = regulate(dict(BASELINE, concern=0.9), {"error_count": 7, "tool_event_count": 10},
                    wins=["research_completed"])
    assert regs[0].direction_key == "report_kevin"
    assert any(r.strategy == "savoring" for r in regs)    # wins still acknowledged, after the problem


def test_every_number_in_a_perspective_comes_from_its_evidence():
    cases = [
        regulate(dict(BASELINE, concern=0.9, fatigue=0.7, uncertainty=0.65),
                 {"error_count": 7, "tool_event_count": 10, "consecutive_errors": 4}),
        regulate(dict(BASELINE, enthusiasm=0.8), {}, open_objectives=6),
        regulate(dict(BASELINE, satisfaction=0.7), {"error_count": 2, "error_rate": 0.2}, lessons=["flattery"]),
    ]
    for regs in cases:
        for r in regs:
            evidence_text = " ".join(f"{v} {v:.0%}" if isinstance(v, float) else str(v) for v in r.evidence.values())
            for number in re.findall(r"\d+", r.perspective):
                assert number in evidence_text, (r.strategy, number, r.perspective)


def test_directions_come_only_from_the_fixed_catalog():
    for dims in (dict(BASELINE), dict(BASELINE, concern=0.9), dict(BASELINE, curiosity=0.1, enthusiasm=0.1)):
        for r in regulate(dims, {"error_count": 1, "tool_event_count": 3}, wins=["gap_found"], lessons=["flattery"]):
            assert r.direction in DIRECTIONS.values()


def test_calm_moment_is_steady():
    assert [r.strategy for r in regulate(dict(BASELINE))] == ["steady"]


# ── check-in end to end, persistence, inner voice ────────────────────────────


def test_a_failing_streak_produces_an_honest_hard_check_in(isolated):
    for i in range(5):
        c = emotional_checkin(events=_tool(False, 12), rewards=[], now=T0 + timedelta(minutes=i), data_dir=isolated)
    assert c.mood.label in ("concerned", "strained", "tired-but-engaged")
    assert any(r.direction_key in ("report_kevin", "name_failure", "checkpoint") for r in c.regulations)
    assert c.inner_voice.endswith(HONESTY_LINE) and len(c.inner_voice) <= 700


def test_real_wins_are_savored_and_persisted(isolated):
    c = emotional_checkin(events=_tool(True, 20) + [{"flag": "commit-d"}] * 3,
                          rewards=[_reward(), _reward("self_correction", points=6.0)], now=T0, data_dir=isolated)
    assert set(c.feed.wins) == {"research_completed", "self_correction"}
    assert any(r.strategy == "savoring" for r in c.regulations)
    assert c.persisted and len(mood_history(isolated)) == 1
    assert mood_history(isolated)[-1]["inner_voice"] == c.inner_voice


def test_torn_last_line_is_skipped_not_fatal(isolated):
    append_mood({"mood": Mood(updated_at=T0.isoformat()).as_dict()}, isolated)
    with open(ledger_path(isolated), "a", encoding="utf-8") as fh:
        fh.write('{"mood": {"dims": {"focus": 0.')          # crash mid-write
    assert len(mood_history(isolated)) == 1
    emotional_checkin(events=[], rewards=[], now=T0 + timedelta(hours=1), data_dir=isolated)


def test_inner_voice_is_bounded_and_always_honest():
    long = regulate(dict(BASELINE), wins=["x" * 2000])
    assert len(inner_voice(Mood(), long)) <= 700 and inner_voice(Mood(), long).endswith(HONESTY_LINE)
    with pytest.raises(ValueError):
        inner_voice(Mood(), [])


# ── maturity report ──────────────────────────────────────────────────────────


def test_report_measures_recovery_from_a_hard_stretch():
    def rec(**dims):
        return {"mood": {"dims": dict(BASELINE, **dims)}, "signals": {"tool_event_count": 5}}
    history = [rec(), rec(concern=0.6), rec(concern=0.55), rec(concern=0.3), rec()]
    r = maturity_report(history)
    assert r.hard_stretches == 1 and r.recovery_updates == 2 and r.pinned_dimensions == []
    assert maturity_report(history[:1]).steadiness is None


def test_report_flags_pinned_dimensions():
    history = [{"mood": {"dims": dict(BASELINE)}}, {"mood": {"dims": dict(BASELINE, satisfaction=0.99)}}]
    assert maturity_report(history).pinned_dimensions == ["satisfaction"]


# ── tools ────────────────────────────────────────────────────────────────────


async def test_tools_check_in_and_report():
    from sovereign_agent.tools.maturity_tools import EmotionalCheckinTool, MaturityReportTool

    checkin = EmotionalCheckinTool()
    assert checkin.tier == 1 and MaturityReportTool().tier == 0
    for _ in range(2):
        res = await checkin.execute(checkin.Args(), trace_id="t")
        assert res.ok, res.error
        assert res.output["inner_voice"].endswith(HONESTY_LINE)
    report = await MaturityReportTool().execute(MaturityReportTool.Args(), trace_id="t")
    assert report.ok and report.output["updates"] == 2


# ── audit events at decision points (observability) ──────────────────────────


def test_escalations_and_ignored_rewards_are_audited(monkeypatch):
    from sovereign_agent import events
    from sovereign_agent.maturity.regulation import ESCALATE_CONCERN
    from sovereign_agent.maturity.reward_feed import CORRECTIVE_WEIGHT

    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(events, "emit_event", lambda flag, **kw: seen.append((flag, kw["payload"])) or "evt")
    regulate(dict(BASELINE, concern=ESCALATE_CONCERN), {"error_count": 3, "tool_event_count": 4})
    reward_nudges([_reward(evidence="")])
    maturity_report([{"mood": {"dims": dict(BASELINE)}}, {"mood": {"dims": dict(BASELINE, fatigue=0.99)}}])
    flags = [f for f, _ in seen]
    assert flags == ["maturity.escalated_to_kevin", "maturity.rewards_limited", "maturity.dimension_pinned"]
    assert 0 < CORRECTIVE_WEIGHT < 1          # mistakes always weigh less than wins


def test_calm_moments_emit_no_alarms(monkeypatch):
    from sovereign_agent import events

    seen: list[str] = []
    monkeypatch.setattr(events, "emit_event", lambda flag, **kw: seen.append(flag) or "evt")
    regulate(dict(BASELINE))
    reward_nudges([_reward()])
    assert seen == []
