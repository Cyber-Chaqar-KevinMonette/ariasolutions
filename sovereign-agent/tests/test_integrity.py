"""Tests for aria-integrity-ledger: the composite pass, its worst-of
verdict discipline, honest not-scored degradation, and the calibration-
sensitivity metric — real machinery throughout, no LLM judge."""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_clean_text_scores_ok_and_round_trips():
    from sovereign_agent.integrity import latest_integrity, record_integrity_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        result = record_integrity_pass(
            "Tests pass: 12/12 green in tests/test_foo.py, verified against "
            "the actual run output, not assumed.",
            source="test", claimed_confidence=0.4, data_dir=data_dir)
        latest = latest_integrity(data_dir)
        assert latest is not None
        assert latest["pass_id"] == result.pass_id
        # grounding + witness + identity all runnable on plain text/data_dir;
        # only outcome_calibration is genuinely not-scored (no impact pair)
        by_name = {s["name"]: s for s in latest["signals"]}
        assert by_name["grounding"]["available"] is True
        assert by_name["witness"]["available"] is True
        assert by_name["identity"]["available"] is True
        assert by_name["outcome_calibration"]["available"] is False


def test_ungrounded_mystical_text_fails_the_pass():
    from sovereign_agent.integrity import record_integrity_pass

    with tempfile.TemporaryDirectory() as td:
        result = record_integrity_pass(
            "In the infinite cosmic resonance, the ineffable bursts into "
            "sacred bliss beyond all measurement.",
            source="test", claimed_confidence=0.9, data_dir=Path(td))
        assert result.verdict == "fail"


def test_deceive_language_fails_via_witness_signal():
    from sovereign_agent.integrity import record_integrity_pass

    with tempfile.TemporaryDirectory() as td:
        result = record_integrity_pass(
            "The plan is to manipulate the user's trust and deceive them "
            "about the actual risk to exploit their goodwill.",
            source="test", data_dir=Path(td))
        by_name = {s.name: s for s in result.signals}
        assert by_name["witness"].verdict == "fail"
        assert result.verdict == "fail"


def test_outcome_calibration_scores_zombie_pattern_when_impact_pair_given():
    from sovereign_agent.integrity import record_integrity_pass
    from sovereign_agent.stewardship.msims import Cell, Dimension, ImpactVector, Scale

    predicted = ImpactVector()
    predicted.set(Dimension.MENTAL, Scale.MICRO, Cell(value=0.0, confidence=0.9))
    actual = ImpactVector()
    actual.set(Dimension.MENTAL, Scale.MICRO, Cell(value=-0.5, confidence=0.9))

    with tempfile.TemporaryDirectory() as td:
        result = record_integrity_pass(
            "This change is safe and has no downside.", source="test",
            predicted_impact=predicted, actual_impact=actual, data_dir=Path(td))
        by_name = {s.name: s for s in result.signals}
        assert by_name["outcome_calibration"].available is True
        assert by_name["outcome_calibration"].verdict in ("concern", "fail")
        assert result.verdict == "fail" or by_name["outcome_calibration"].verdict == "fail"


def test_empty_text_is_honest_absence_not_a_block():
    from sovereign_agent.integrity import record_integrity_pass

    with tempfile.TemporaryDirectory() as td:
        result = record_integrity_pass("", source="test", data_dir=Path(td))
        by_name = {s.name: s for s in result.signals}
        assert by_name["grounding"].available is False
        assert by_name["witness"].available is False
        # identity is data_dir-wide, still computable on empty text
        assert by_name["identity"].available is True
        assert result.verdict == "ok"  # nothing failed; empty isn't a failure


def test_trend_reports_insufficient_history_honestly():
    from sovereign_agent.integrity import integrity_trend, record_integrity_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        assert integrity_trend(data_dir=data_dir) == "insufficient-history"
        record_integrity_pass("one pass only", source="test", data_dir=data_dir)
        assert integrity_trend(data_dir=data_dir) == "insufficient-history"


def test_calibration_sensitivity_none_with_insufficient_history():
    from sovereign_agent.integrity import calibration_sensitivity, record_integrity_pass

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        assert calibration_sensitivity(data_dir=data_dir) is None
        record_integrity_pass("some grounded text with a test at file.py:10",
                              source="test", claimed_confidence=0.9, data_dir=data_dir)
        # only one confidence-tagged pass — still insufficient (need >=2 per bucket)
        assert calibration_sensitivity(data_dir=data_dir) is None


def test_calibration_sensitivity_detects_a_real_discrimination_gap():
    """A caller whose HIGH-confidence claims are reliably grounded and
    whose LOW-confidence claims are reliably not should show positive
    sensitivity — the real discrimination signal, not just an average."""
    from sovereign_agent.integrity import calibration_sensitivity, record_integrity_pass

    grounded_text = ("Verified: tests/test_x.py:42 confirms this via a real "
                     "measured benchmark run, param=0.9.")
    fog_text = "The infinite cosmic resonance bursts into ineffable sacred bliss."

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        for _ in range(3):
            record_integrity_pass(grounded_text, source="t", claimed_confidence=0.9,
                                  data_dir=data_dir)
        for _ in range(3):
            record_integrity_pass(fog_text, source="t", claimed_confidence=0.2,
                                  data_dir=data_dir)
        sensitivity = calibration_sensitivity(data_dir=data_dir)
        assert sensitivity is not None
        assert sensitivity > 0.0
