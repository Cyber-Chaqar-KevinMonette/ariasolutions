"""Tests for non-classical god-tier parity — robustness + the parity benchmark vs classical."""
from __future__ import annotations

import asyncio


# ── robustness (god-tier hardening) ───────────────────────────────────────────

def test_determinism():
    from sovereign_agent.nonclassical import robustness
    assert robustness.check_determinism()["ok"]            # same seed → same curve


def test_graceful_degradation_never_crashes():
    from sovereign_agent.nonclassical import robustness
    deg = robustness.check_graceful_degradation()
    assert deg["ok"]                                       # empty/tiny/default corpora all run
    assert all(c["ok"] for c in deg["cases"])


def test_bounded_learning_in_range():
    from sovereign_agent.nonclassical import robustness
    b = robustness.check_bounded_learning()
    assert b["ok"] and b["in_range"]                       # word_acc stays in [0,1]


def test_robustness_scan_certifies():
    from sovereign_agent.nonclassical import robustness
    assert robustness.robustness_scan()["god_tier_robust"] is True


# ── parity (measured, not claimed) ────────────────────────────────────────────

def test_parity_on_par_or_better():
    from sovereign_agent.nonclassical import parity
    p = parity.benchmark(epochs=30, trials=2)
    assert p["available"]
    assert 0.0 <= p["non_classical_word_acc"] <= 1.0
    assert 0.0 <= p["classical_baseline_word_acc"] <= 1.0
    assert p["on_par_or_better"] is True                   # non-classical is at least on par on this task
    assert p["verdict"] in ("on par", "non-classical BETTER")


# ── tool ──────────────────────────────────────────────────────────────────────

def test_nonclassical_certify_tool():
    from sovereign_agent.tools.nonclassical_tools import NonClassicalCertifyTool
    assert NonClassicalCertifyTool.tier == 0
    r = asyncio.run(NonClassicalCertifyTool().execute(NonClassicalCertifyTool.Args(epochs=20), trace_id="t"))
    assert r.ok and "certified_god_tier" in r.output and "parity" in r.output
