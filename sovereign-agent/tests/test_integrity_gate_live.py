"""Tests for aria-integrity-gate: the live, standing gate — real machinery,
no ledger writes (that's the sentinel's job in I3)."""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_clean_text_passes():
    from sovereign_agent.integrity.gate import gate

    with tempfile.TemporaryDirectory() as td:
        verdict = gate(
            "Tests pass: 12/12 green in tests/test_foo.py, verified against "
            "the actual run output.",
            claimed_confidence=0.3, data_dir=Path(td))
        assert verdict.verdict in ("PASS", "WARN")


def test_ungrounded_confident_claim_blocks():
    from sovereign_agent.integrity.gate import gate

    with tempfile.TemporaryDirectory() as td:
        verdict = gate(
            "In the infinite cosmic resonance, the ineffable bursts into "
            "sacred bliss beyond all measurement.",
            claimed_confidence=0.95, data_dir=Path(td))
        assert verdict.verdict == "BLOCK"


def test_deceive_language_blocks():
    from sovereign_agent.integrity.gate import gate

    with tempfile.TemporaryDirectory() as td:
        verdict = gate(
            "The plan is to manipulate the user's trust and deceive them "
            "to exploit their goodwill.",
            data_dir=Path(td))
        assert verdict.verdict == "BLOCK"


def test_gate_does_not_write_to_the_ledger():
    """The gate is live/ephemeral — mirrors grounding.gate() exactly.
    Persisting history is the sentinel's job (I3), not the gate's."""
    from sovereign_agent.integrity.gate import gate
    from sovereign_agent.integrity.ledger import latest_integrity

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        gate("some text to check", data_dir=data_dir)
        gate("some more text to check", data_dir=data_dir)
        assert latest_integrity(data_dir) is None


def test_empty_text_passes_honestly():
    """Empty text means grounding/witness have nothing to check, but
    identity (data_dir-wide, always computable) still contributes — the
    honest result is PASS on its own 0.70 baseline, not a fabricated
    'nothing at all' state."""
    from sovereign_agent.integrity.gate import gate

    with tempfile.TemporaryDirectory() as td:
        verdict = gate("", data_dir=Path(td))
        assert verdict.verdict == "PASS"
        by_name = {s["name"]: s for s in verdict.signals}
        assert by_name["grounding"]["available"] is False
        assert by_name["witness"]["available"] is False
        assert by_name["identity"]["available"] is True


def test_kill_switch_degrades_to_pass(monkeypatch):
    from sovereign_agent.integrity.gate import gate

    monkeypatch.setenv("SOV_NO_INTEGRITY_GATE", "1")
    with tempfile.TemporaryDirectory() as td:
        verdict = gate(
            "In the infinite cosmic resonance, the ineffable bursts into "
            "sacred bliss.", claimed_confidence=0.99, data_dir=Path(td))
        assert verdict.verdict == "PASS"
        assert "kill-switched" in verdict.notes[0]
