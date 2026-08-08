"""aria-grounding-tribunal — standing audit + measured skeptic lens.
(Grounding round · G3)

All three patched files (tribunal/tribunal.py, spectrum/lenses.py,
stewardship/grounding_sentinel.py) are IN-PLACE patches to existing,
already-live files — patch-dependent, skip honestly pre-apply; the apply
script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect

MOSTLY_EVIDENCE = (
    "The test suite passed 412 of 412 tests after the fix in loader.py. "
    "Latency dropped from 220ms to 90ms, measured across 50 runs."
)


def _patched(obj) -> bool:
    return "grounding-tribunal-d" in inspect.getsource(obj)


# ─── (1) log_to_diagnosis gains an optional prefix ────────────────────────


def test_log_to_diagnosis_defaults_to_trib_prefix_unchanged(tmp_path):
    import pytest

    from sovereign_agent import tribunal as tribunal_mod

    if not _patched(tribunal_mod.tribunal):
        pytest.skip("pre-apply: tribunal.py not yet patched")
    from sovereign_agent.tribunal import convene
    from sovereign_agent.tribunal.tribunal import log_to_diagnosis

    verdict = convene({"text": "a small, reversible, well-tested change"},
                      include_kernel=False)
    case_id = log_to_diagnosis({"change": "default prefix check"}, verdict, tmp_path)
    assert case_id is not None
    assert case_id.startswith("TRIB")


def test_log_to_diagnosis_honors_a_custom_prefix(tmp_path):
    import pytest

    from sovereign_agent import tribunal as tribunal_mod

    if not _patched(tribunal_mod.tribunal):
        pytest.skip("pre-apply: tribunal.py not yet patched")
    from sovereign_agent.diagnosis import ConflictCatalog
    from sovereign_agent.tribunal import convene
    from sovereign_agent.tribunal.tribunal import log_to_diagnosis

    verdict = convene({"text": "a small, reversible, well-tested change"},
                      include_kernel=False)
    case_id = log_to_diagnosis({"change": "custom prefix check"}, verdict, tmp_path,
                               prefix="GRND")
    assert case_id is not None
    assert case_id.startswith("GRND")

    cat = ConflictCatalog(tmp_path / "diagnosis")
    conflict = cat.get_conflict(case_id)
    assert conflict is not None
    assert conflict.type == "ambiguity"


# ─── (2) skeptic lens: measured composite over live-only ─────────────────


def test_skeptic_unaffected_when_no_measured_keys_present():
    from sovereign_agent.spectrum.lenses import skeptic

    read = skeptic(MOSTLY_EVIDENCE)
    assert read.lens == "skeptic"
    # falls through to the ORIGINAL live-only path — no measured branch taken
    assert "grounding:" in read.gifts[0]


def test_skeptic_prefers_the_measured_grounding_verdict():
    import pytest

    from sovereign_agent.spectrum.lenses import skeptic

    if not _patched(skeptic):
        pytest.skip("pre-apply: skeptic lens not yet patched")
    high = skeptic({"grounding_verdict": "grounded", "epistemic_score": 0.9,
                    "qa_calibration_ok": True})
    assert high.score > 0.5
    assert any("measured" in g for g in high.gifts)

    low = skeptic({"grounding_verdict": "ungrounded", "epistemic_score": 0.1,
                   "qa_calibration_ok": True})
    assert low.score < 0.0


def test_skeptic_measured_calibration_break_forces_a_low_score():
    import pytest

    from sovereign_agent.spectrum.lenses import skeptic

    if not _patched(skeptic):
        pytest.skip("pre-apply: skeptic lens not yet patched")
    read = skeptic({"grounding_verdict": "grounded", "epistemic_score": 0.9,
                    "qa_calibration_ok": False})
    assert read.score <= -0.6
    assert any("calibration" in c for c in read.concerns)


def test_skeptic_prose_fallback_still_works_with_a_plain_dict():
    import pytest

    from sovereign_agent.spectrum.lenses import skeptic

    if not _patched(skeptic):
        pytest.skip("pre-apply: skeptic lens not yet patched")
    read = skeptic({"text": MOSTLY_EVIDENCE})
    assert "grounding:" in read.gifts[0]


# ─── (3) the standing scan phase ──────────────────────────────────────────


def test_sentinel_standing_phase_logs_a_grnd_diagnosis_case(tmp_path):
    import pytest

    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    if not _patched(GroundingSentinel):
        pytest.skip("pre-apply: grounding_sentinel.py standing phase not yet patched")

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(MOSTLY_EVIDENCE, encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    sentinel.scan()

    standing = sentinel.load_catalog(name="standing-audit")
    assert standing is not None
    assert standing.get("case_id", "").startswith("GRND")

    from sovereign_agent.diagnosis import ConflictCatalog

    cat = ConflictCatalog(tmp_path / "diagnosis")
    conflict = cat.get_conflict(standing["case_id"])
    assert conflict is not None
    assert conflict.type == "ambiguity"


def test_sentinel_standing_phase_never_breaks_the_scan_on_failure(tmp_path, monkeypatch):
    """Even if the standing-audit phase itself explodes, scan() must still
    return a real report — it's best-effort, never load-bearing for the
    grounding pass itself."""
    import pytest

    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    if not _patched(GroundingSentinel):
        pytest.skip("pre-apply: grounding_sentinel.py standing phase not yet patched")

    import sovereign_agent.tribunal as tribunal_pkg

    def _boom(*a, **k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(tribunal_pkg, "convene", _boom)

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / "2026-07-04.md").write_text(MOSTLY_EVIDENCE, encoding="utf-8")

    sentinel = GroundingSentinel(tmp_path)
    report = sentinel.scan()   # must not raise
    assert report is not None


def test_sentinel_standing_phase_skips_cleanly_with_nothing_to_score(tmp_path):
    import pytest

    from sovereign_agent.stewardship.grounding_sentinel import GroundingSentinel

    if not _patched(GroundingSentinel):
        pytest.skip("pre-apply: grounding_sentinel.py standing phase not yet patched")

    sentinel = GroundingSentinel(tmp_path)
    report = sentinel.scan()
    assert report is not None
    assert sentinel.load_catalog(name="standing-audit") is None
