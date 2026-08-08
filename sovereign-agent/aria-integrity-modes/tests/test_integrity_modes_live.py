"""Tests for aria-integrity-modes: the "honest" stance — a real action on
entry, gated dispatch via integrity_gate_clear(). All three patched files
are in-place edits to already-live modules, so these tests only pass
post-apply — same discipline as aria-quality-modes/aria-grounding-modes/
aria-wellbeing-modes before it."""
from __future__ import annotations

from pathlib import Path


def _write_journal(data_dir: Path, name: str, text: str) -> None:
    journal_dir = data_dir / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    (journal_dir / f"{name}.md").write_text(text, encoding="utf-8")


def test_honest_is_a_safe_stance():
    from sovereign_agent.modes_crown.stances import SAFE_STANCES

    assert "honest" in SAFE_STANCES


def test_entering_honest_over_clean_journal_clears_immediately(tmp_path):
    from sovereign_agent.modes_crown.stances import integrity_gate_clear, set_stance

    _write_journal(tmp_path, "2026-07-06",
                   "Verified: tests/test_x.py:42 confirms this via a real "
                   "measured benchmark run.")
    set_stance("honest", data_dir=tmp_path)
    assert integrity_gate_clear(tmp_path) is True


def test_entering_honest_over_mystical_journal_stays_blocked(tmp_path):
    from sovereign_agent.modes_crown.stances import integrity_gate_clear, set_stance

    _write_journal(tmp_path, "2026-07-06",
                   "In the infinite cosmic resonance, the ineffable bursts "
                   "into sacred bliss beyond all measurement.")
    set_stance("honest", data_dir=tmp_path)
    assert integrity_gate_clear(tmp_path) is False


def test_gate_clear_true_when_not_in_honest_stance(tmp_path):
    from sovereign_agent.modes_crown.stances import integrity_gate_clear, set_stance

    set_stance("planning", data_dir=tmp_path)
    assert integrity_gate_clear(tmp_path) is True


def test_entering_honest_actually_records_a_ledger_pass(tmp_path):
    from sovereign_agent.integrity import latest_integrity
    from sovereign_agent.modes_crown.stances import set_stance

    _write_journal(tmp_path, "2026-07-06", "A plain unremarkable entry with no claims.")
    before = latest_integrity(tmp_path)
    assert before is None
    set_stance("honest", data_dir=tmp_path)
    after = latest_integrity(tmp_path)
    assert after is not None
