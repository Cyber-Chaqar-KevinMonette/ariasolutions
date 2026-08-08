"""Real behavior tests for aria-wholeness-gate — the guardian that keeps her
whole when no one is watching. These prove it (a) gives an honest whole/
not-whole verdict, and (b) catches EVERY direction of regression while never
false-alarming on an improvement or an unmeasured dimension.
"""
from __future__ import annotations

from sovereign_agent.wholeness_gate import (
    WholenessMetrics,
    check_regression,
    load_baseline,
    snapshot_baseline,
    wholeness_verdict,
)


def _whole():
    return WholenessMetrics(
        god_tier_fraction=0.67, average_score=0.83, total_targets=215,
        sentinel_total=23, sentinel_errors=0, unexplained_timeouts=0,
        self_map_orphans=0, smoke_gates_pass=True, floor_check_met=True,
    )


# ── wholeness_verdict ────────────────────────────────────────────────────
def test_a_healthy_snapshot_is_whole():
    v = wholeness_verdict(_whole())
    assert v["whole"] is True
    assert v["failing"] == []


def test_low_god_tier_fraction_is_not_whole():
    m = _whole(); m.god_tier_fraction = 0.50
    v = wholeness_verdict(m)
    assert v["whole"] is False
    assert "god_tier" in v["failing"]


def test_a_sentinel_error_is_not_whole():
    m = _whole(); m.sentinel_errors = 1
    v = wholeness_verdict(m)
    assert v["whole"] is False and "sentinel_errors" in v["failing"]


def test_unexplained_timeout_is_not_whole():
    m = _whole(); m.unexplained_timeouts = 2
    assert wholeness_verdict(m)["whole"] is False


def test_broken_smoke_gate_is_not_whole():
    m = _whole(); m.smoke_gates_pass = False
    v = wholeness_verdict(m)
    assert v["whole"] is False and "smoke_gates" in v["failing"]


def test_unmeasured_gate_does_not_fail_the_verdict():
    # A fast check that skips the heavy smoke gates is still meaningful:
    # None gates are 'unknown', excluded from the call, not a failure.
    m = _whole(); m.smoke_gates_pass = None; m.floor_check_met = None
    v = wholeness_verdict(m)
    assert v["whole"] is True
    assert "smoke_gates" not in v["checks"]  # not even reported when unknown


# ── check_regression (the guardian core) ─────────────────────────────────
def test_identical_snapshot_is_no_regression():
    assert check_regression(_whole(), _whole())["regressed"] is False


def test_god_tier_fraction_dropping_is_a_regression():
    cur = _whole(); cur.god_tier_fraction = 0.60
    r = check_regression(cur, _whole())
    assert r["regressed"] is True
    assert any(f["dimension"] == "god_tier_fraction" for f in r["findings"])


def test_a_disappearing_sentinel_is_a_regression():
    cur = _whole(); cur.sentinel_total = 22  # one sentinel vanished
    r = check_regression(cur, _whole())
    assert r["regressed"] is True
    assert any(f["dimension"] == "sentinel_total" for f in r["findings"])


def test_rising_errors_and_timeouts_and_orphans_regress():
    cur = _whole()
    cur.sentinel_errors = 1
    cur.unexplained_timeouts = 1
    cur.self_map_orphans = 3
    findings = check_regression(cur, _whole())["findings"]
    dims = {f["dimension"] for f in findings}
    assert {"sentinel_errors", "unexplained_timeouts", "self_map_orphans"} <= dims


def test_a_gate_breaking_is_a_regression():
    cur = _whole(); cur.smoke_gates_pass = False
    r = check_regression(cur, _whole())
    assert any(f["kind"] == "gate-broke" for f in r["findings"])


def test_an_improvement_is_never_a_regression():
    cur = _whole()
    cur.god_tier_fraction = 0.80        # better
    cur.sentinel_total = 25             # gained sentinels
    cur.average_score = 0.90            # better
    assert check_regression(cur, _whole())["regressed"] is False


def test_tiny_float_noise_is_not_a_regression():
    cur = _whole(); cur.god_tier_fraction = 0.67 - 0.001  # within tolerance
    assert check_regression(cur, _whole())["regressed"] is False


def test_unknown_gate_now_is_not_counted_as_broken():
    base = _whole()                     # smoke_gates_pass True
    cur = _whole(); cur.smoke_gates_pass = None   # simply not measured now
    r = check_regression(cur, base)
    assert not any(f["dimension"] == "smoke_gates_pass" for f in r["findings"])


# ── persistence ──────────────────────────────────────────────────────────
def test_baseline_round_trips(tmp_path):
    path = tmp_path / "wholeness_baseline.json"
    snapshot_baseline(_whole(), path)
    loaded = load_baseline(path)
    assert loaded is not None
    assert loaded.god_tier_fraction == 0.67
    assert loaded.sentinel_total == 23
    assert check_regression(loaded, _whole())["regressed"] is False


def test_missing_baseline_returns_none(tmp_path):
    assert load_baseline(tmp_path / "nope.json") is None


def test_corrupt_baseline_does_not_crash_the_guard(tmp_path):
    p = tmp_path / "bad.json"; p.write_text("{ not valid json", encoding="utf-8")
    assert load_baseline(p) is None  # degrades, never raises
