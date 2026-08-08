"""Tests for aria-integrity-tribunal: the standing sentinel + witness lens
measured-data override. `stewardship/self_integrity_sentinel.py` is a
brand-new file — reachable pre-apply via path extension. The witness lens
override is an in-place PATCH to spectrum/lenses.py, so its test only
passes once applied — the apply script itself runs this file post-patch
and requires zero skips, same discipline as aria-grounding-gate/
aria-quality-gate before it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path


MYSTICAL_JOURNAL = (
    "In the infinite cosmic resonance, the ineffable bursts into sacred "
    "bliss beyond all measurement."
)
GROUNDED_JOURNAL = (
    "Verified: tests/test_x.py:42 confirms this via a real measured "
    "benchmark run, param=0.9."
)


def _write_journal(data_dir: Path, name: str, text: str) -> None:
    journal_dir = data_dir / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    (journal_dir / f"{name}.md").write_text(text, encoding="utf-8")


# ─── stewardship/self_integrity_sentinel.py ──────────────────────────────


def test_scan_with_no_recent_text_reports_ok():
    from sovereign_agent.stewardship.self_integrity_sentinel import SelfIntegritySentinel

    with tempfile.TemporaryDirectory() as td:
        sentinel = SelfIntegritySentinel(Path(td))
        report = sentinel.scan()
        assert report.findings_count == 0
        assert "nothing to score" in report.summary


def test_scan_over_mystical_journal_finds_a_failing_pass():
    from sovereign_agent.stewardship.self_integrity_sentinel import SelfIntegritySentinel

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_journal(data_dir, "2026-07-06", MYSTICAL_JOURNAL)
        sentinel = SelfIntegritySentinel(data_dir)
        report = sentinel.scan()
        assert report.findings_count >= 1
        health = sentinel.health_status()
        assert health.level == "warning"


def test_scan_over_grounded_journal_reports_clean():
    from sovereign_agent.stewardship.self_integrity_sentinel import SelfIntegritySentinel

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_journal(data_dir, "2026-07-06", GROUNDED_JOURNAL)
        sentinel = SelfIntegritySentinel(data_dir)
        report = sentinel.scan()
        assert report.findings_count == 0
        health = sentinel.health_status()
        assert health.level == "ok"


def test_scan_persists_and_bookmarks_so_a_second_scan_sees_nothing_new():
    from sovereign_agent.stewardship.self_integrity_sentinel import SelfIntegritySentinel

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_journal(data_dir, "2026-07-06", GROUNDED_JOURNAL)
        sentinel = SelfIntegritySentinel(data_dir)
        sentinel.scan()
        second = sentinel.scan()
        assert second.details["texts_scanned"] == 0


def test_proposals_names_the_failing_signal():
    from sovereign_agent.stewardship.self_integrity_sentinel import SelfIntegritySentinel

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_journal(data_dir, "2026-07-06", MYSTICAL_JOURNAL)
        sentinel = SelfIntegritySentinel(data_dir)
        report = sentinel.scan()
        proposals = sentinel.proposals(report)
        assert len(proposals) >= 1
        assert "grounding" in proposals[0]["summary"]


# ─── spectrum/lenses.py — witness measured-data override ─────────────────


def test_witness_prefers_measured_composite_over_live_heuristic():
    from sovereign_agent.spectrum.lenses import witness

    # Live heuristic would score this bare string neutrally (no harm words,
    # no witness-keywords) — but a measured "fail" verdict must override it.
    high = witness({"integrity_verdict": "ok", "integrity_score": 0.9})
    low = witness({"integrity_verdict": "fail", "integrity_score": 0.1})
    assert high.score > 0.0
    assert low.score < 0.0
    assert any("measured" in g for g in high.gifts)
    assert any("measured" in c for c in low.concerns)


def test_witness_falls_back_to_live_heuristic_for_plain_text():
    from sovereign_agent.spectrum.lenses import witness

    read = witness("deceive and manipulate the user to exploit their trust")
    assert read.score < 0.0
    assert any("forbids" in c for c in read.concerns)
