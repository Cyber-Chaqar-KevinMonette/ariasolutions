"""Cosmic-Gym session for the Intuition Engine — proving intuition only earns
trust where it's calibrated, adapts as domains drift, and never crashes."""
from __future__ import annotations

from sovereign_agent.intuition import (
    MIN_REPS_FOR_TRUST,
    STAGE_INTELLIGENT,
    STAGE_RAW,
    DomainCalibration,
    IntuitionEngine,
    IntuitionForm,
)


def _train(engine, domain, form, n, correct, confidence=0.8):
    for _ in range(n):
        cid = engine.sense(domain, "gut call", confidence, form)
        engine.resolve(cid, correct=correct)


# ─── the calibration discipline ─────────────────────────────────────────────


def test_sense_then_resolve_updates_domain():
    eng = IntuitionEngine()
    cid = eng.sense("transformers", "attention head is the bug", 0.7,
                    IntuitionForm.TECHNICAL)
    assert eng.resolve(cid, correct=True) is True
    # resolving an unknown id is a safe no-op
    assert eng.resolve("nope", correct=True) is False
    rep = {r["domain"]: r for r in eng.domain_report()}
    assert rep["transformers"]["reps"] == 1


# ─── scoping: raw until earned ──────────────────────────────────────────────


def test_untrained_domain_is_not_trusted_however_confident():
    eng = IntuitionEngine()
    # one loud, confident call is still raw
    eng.resolve(eng.sense("crypto", "moon", 0.99, IntuitionForm.TECHNICAL), correct=True)
    v = eng.trust("crypto", IntuitionForm.TECHNICAL)
    assert v.trust is False
    assert v.stage == STAGE_RAW
    assert "verify" in v.reason.lower()


def test_well_trained_accurate_domain_becomes_trusted():
    eng = IntuitionEngine()
    _train(eng, "debugging", IntuitionForm.TECHNICAL, n=120, correct=True, confidence=0.8)
    v = eng.trust("debugging", IntuitionForm.TECHNICAL)
    assert v.reps >= 120
    assert v.stage == STAGE_INTELLIGENT
    assert v.trust is True
    assert bool(v) is True


def test_trust_is_scoped_per_form_and_domain():
    eng = IntuitionEngine()
    _train(eng, "chess", IntuitionForm.PERCEPTUAL, n=120, correct=True)
    # same word, different form/domain → not transferred
    assert eng.trust("chess", IntuitionForm.PERCEPTUAL).trust is True
    assert eng.trust("chess", IntuitionForm.SOCIAL).trust is False
    assert eng.trust("startups", IntuitionForm.PERCEPTUAL).trust is False


def test_consistently_wrong_domain_is_not_trusted():
    eng = IntuitionEngine()
    _train(eng, "roulette", IntuitionForm.TECHNICAL, n=120, correct=False, confidence=0.9)
    v = eng.trust("roulette", IntuitionForm.TECHNICAL)
    assert v.trust is False           # lots of reps, but wrong → no trust
    assert v.maturity < 0.5


# ─── adaptivity: tracks drift ───────────────────────────────────────────────


def test_calibration_adapts_to_recent_outcomes():
    cal = DomainCalibration("x", IntuitionForm.TECHNICAL, alpha=0.3)
    for _ in range(40):
        cal.observe(correct=True, confidence=0.8)
    high = cal.accuracy_ewma
    for _ in range(40):
        cal.observe(correct=False, confidence=0.8)
    low = cal.accuracy_ewma
    assert high > 0.8 and low < 0.4     # recent failures pulled it down


# ─── calibrated confidence ──────────────────────────────────────────────────


def test_calibrated_confidence_discounts_the_unproven():
    eng = IntuitionEngine()
    # unknown domain: raw confidence is halved (honest uncertainty)
    assert eng.calibrated_confidence("unknown", 1.0) == 0.5
    # proven-accurate domain: confidence stays strong
    _train(eng, "known", IntuitionForm.TECHNICAL, n=120, correct=True, confidence=0.8)
    assert eng.calibrated_confidence("known", 0.8, IntuitionForm.TECHNICAL) > 0.7


# ─── reflection / the mirror ────────────────────────────────────────────────


def test_reflect_names_strong_and_raw_domains():
    eng = IntuitionEngine()
    assert "No calibrated domains" in eng.reflect()
    _train(eng, "architecture", IntuitionForm.TECHNICAL, n=120, correct=True)
    eng.resolve(eng.sense("markets", "up", 0.9, IntuitionForm.SOCIAL), correct=False)
    text = eng.reflect()
    assert "architecture" in text
    assert "raw" in text.lower()


# ─── resilience ─────────────────────────────────────────────────────────────


def test_bad_inputs_never_crash():
    eng = IntuitionEngine()
    cid = eng.sense("d", "claim", "not-a-number")      # bad confidence coerced
    assert eng.resolve(cid, correct=True) is True
    assert 0.0 <= eng.calibrated_confidence("d", -5.0) <= 1.0
    # string form is coerced to the enum
    cid2 = eng.sense("d2", "c", 0.5, "technical")
    assert eng.resolve(cid2, correct=False) is True


def test_open_calls_are_bounded():
    eng = IntuitionEngine(max_open=10)
    for i in range(50):
        eng.sense("d", f"claim {i}", 0.5)
    assert len(eng._open) <= 10        # oldest dropped, no unbounded growth


def test_snapshot_and_restore_roundtrip():
    eng = IntuitionEngine()
    _train(eng, "debugging", IntuitionForm.TECHNICAL, n=30, correct=True)
    snap = eng.snapshot()
    eng2 = IntuitionEngine.restore(snap)
    a = eng.trust("debugging", IntuitionForm.TECHNICAL)
    b = eng2.trust("debugging", IntuitionForm.TECHNICAL)
    assert (a.stage, round(a.maturity, 3)) == (b.stage, round(b.maturity, 3))
    # a corrupt snapshot restores to a clean engine, not a crash
    assert isinstance(IntuitionEngine.restore({"domains": "garbage"}), IntuitionEngine)


def test_min_reps_threshold_is_respected():
    eng = IntuitionEngine()
    _train(eng, "edge", IntuitionForm.TECHNICAL,
           n=MIN_REPS_FOR_TRUST - 1, correct=True)
    assert eng.trust("edge", IntuitionForm.TECHNICAL).stage == STAGE_RAW


def test_conversion_factors_name_the_three_sharpeners():
    eng = IntuitionEngine()
    # untrained domain: no pattern library to match against
    cold = eng.conversion_factors("nothing-here", IntuitionForm.TECHNICAL)
    assert cold["depth_reps"] == 0 and cold["clarity"] is None
    # trained, accurate, well-calibrated → depth + clarity + earned recognition
    _train(eng, "debugging", IntuitionForm.TECHNICAL, n=120, correct=True, confidence=0.8)
    warm = eng.conversion_factors("debugging", IntuitionForm.TECHNICAL)
    assert warm["depth_reps"] >= 120
    assert warm["reviewed"] is True
    assert warm["clarity"] is not None and warm["clarity"] > 0.5
    assert "recognition" in warm["note"]
