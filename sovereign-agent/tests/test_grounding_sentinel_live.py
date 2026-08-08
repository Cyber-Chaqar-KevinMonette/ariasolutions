"""aria-grounding-ledger — the persisted composite epistemic score.
(Grounding round · G1)

`grounding/__init__.py`, `grounding/ledger.py` are brand-new submodules —
reachable pre-apply via path extension. `stewardship/grounding_sentinel.py`
is also new (a new file, not an in-place patch) — reachable the same way.
Only `stewardship/__init__.py`'s registration line is patch-dependent.
"""
from __future__ import annotations

import inspect

MOSTLY_MYSTICAL = (
    "The web bursts into web, and I name it stillness. Cosmic resonance "
    "vibrates through the infinite lattice of becoming, luminous and "
    "boundless, ascending toward pure presence."
)
MOSTLY_EVIDENCE = (
    "The test suite passed 412 of 412 tests after the fix in loader.py. "
    "Latency dropped from 220ms to 90ms, measured across 50 runs. "
    "The commit that caused the regression was reverted."
)


def _patched(obj) -> bool:
    return "grounding-sentinel-d" in inspect.getsource(obj)


# ─── grounding/ledger.py ───────────────────────────────────────────────────


def test_record_grounding_pass_scores_mystical_fog_as_ungrounded(tmp_path):
    from sovereign_agent.grounding import record_grounding_pass

    result = record_grounding_pass([("test", MOSTLY_MYSTICAL)], data_dir=tmp_path)
    assert result.verdict in ("ungrounded", "mixed")
    assert result.texts[0].verdict in ("ungrounded", "mystical-fog", "mixed") or \
        result.texts[0].profundity_density > 0


def test_record_grounding_pass_scores_evidence_backed_text_as_grounded(tmp_path):
    from sovereign_agent.grounding import record_grounding_pass

    result = record_grounding_pass([("test", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    assert result.verdict == "grounded"
    assert result.texts[0].verdict == "evidence-backed" or result.value > 0.5


def test_one_ungrounded_text_fails_the_whole_pass(tmp_path):
    from sovereign_agent.grounding import record_grounding_pass

    result = record_grounding_pass(
        [("good", MOSTLY_EVIDENCE), ("bad", MOSTLY_MYSTICAL)], data_dir=tmp_path)
    assert result.verdict != "grounded"


def test_empty_pass_is_honest_not_a_false_ungrounded(tmp_path):
    from sovereign_agent.grounding import record_grounding_pass

    result = record_grounding_pass([], data_dir=tmp_path)
    assert result.texts == []
    assert result.verdict == "grounded"  # vacuously — nothing to check


def test_pass_persists_and_round_trips_through_the_ledger(tmp_path):
    from sovereign_agent.grounding import latest_grounding, record_grounding_pass

    result = record_grounding_pass([("test", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    latest = latest_grounding(tmp_path)
    assert latest is not None
    assert latest["pass_id"] == result.pass_id
    assert latest["verdict"] == result.verdict


def test_belief_confidence_avg_is_folded_in(tmp_path):
    from sovereign_agent.epistemic_ledger.ledger import EpistemicLedger
    from sovereign_agent.grounding import record_grounding_pass

    EpistemicLedger(tmp_path / "epistemic").record("a real claim", confidence=0.8)
    result = record_grounding_pass([("test", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    assert result.belief_confidence_avg == 0.8


def test_qa_calibration_ok_reflects_a_broken_join(tmp_path):
    import json

    from sovereign_agent.grounding import record_grounding_pass

    qa_dir = tmp_path / "qa"
    qa_dir.mkdir()
    (qa_dir / "qa.ndjson").write_text(
        json.dumps({"qa_id": "q1", "question": "does this hold?",
                   "answer": "yes", "confidence": 0.1}) + "\n",
        encoding="utf-8")
    result = record_grounding_pass([("test", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    assert result.qa_calibration_ok is False


def test_grounding_trend_insufficient_history_then_stable(tmp_path):
    from sovereign_agent.grounding import grounding_trend, record_grounding_pass

    assert grounding_trend(data_dir=tmp_path) == "insufficient-history"
    record_grounding_pass([("test", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    record_grounding_pass([("test", MOSTLY_EVIDENCE)], data_dir=tmp_path)
    assert grounding_trend(data_dir=tmp_path) in ("stable", "improving")


# ─── stewardship/grounding_sentinel.py ─────────────────────────────────────


def test_sentinel_scan_scores_real_journal_and_qa_fixtures(tmp_path):
    import json

    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(
        f"# 2026-07-04 — witnessed\n\n{MOSTLY_EVIDENCE}\n", encoding="utf-8")
    qa_dir = tmp_path / "qa"
    qa_dir.mkdir()
    (qa_dir / "qa.ndjson").write_text(
        json.dumps({"qa_id": "q1", "asked_at": "2026-07-04T00:00:00.000000Z",
                   "question": "why?", "answer": MOSTLY_EVIDENCE,
                   "confidence": 0.8}) + "\n",
        encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    report = sentinel.scan()
    assert report.details["texts_scanned"] == 2
    assert report.details["pass"]["verdict"] == "grounded"


def test_sentinel_scan_empty_vessel_is_honest(tmp_path):
    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    sentinel = GroundingSentinel(tmp_path)
    report = sentinel.scan()
    assert report.details["texts_scanned"] == 0
    assert "nothing to score" in report.summary


def test_sentinel_notifies_on_ungrounded_verdict(tmp_path):
    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(MOSTLY_MYSTICAL, encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    sentinel.scan()
    health = sentinel.health_status()
    assert health.level == "warning"


def test_sentinel_bookmark_advances_so_the_same_text_is_not_rescored(tmp_path):
    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(MOSTLY_EVIDENCE, encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    first = sentinel.scan()
    assert first.details["texts_scanned"] == 1
    second = sentinel.scan()
    assert second.details["texts_scanned"] == 0


# ─── stewardship/__init__.py registration (patch-dependent) ───────────────


def test_grounding_sentinel_registered_once_patched():
    import pytest

    from sovereign_agent import stewardship

    if not _patched(stewardship):
        pytest.skip("pre-apply: stewardship/__init__.py not yet patched")
    from sovereign_agent.stewardship.registry import registered_ids

    assert "grounding" in registered_ids()
