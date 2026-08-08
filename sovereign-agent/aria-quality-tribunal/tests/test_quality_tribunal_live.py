"""aria-quality-tribunal — advocates and audits, made standing.
(Quality round · Q3)

`quality/review.py` is a brand-new submodule inside the already-live
`quality/` package — reachable pre-apply via path extension. The bug fix
in tribunal/tribunal.py, the artisan-lens patch in spectrum/lenses.py,
and the standing-audit phase in stewardship/quality_sentinel.py are all
IN-PLACE patches to existing files — patch-dependent, skip honestly
pre-apply; the apply script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect


def _patched(obj) -> bool:
    return "quality-tribunal-d" in inspect.getsource(obj)


# ─── (a) the dormant log_to_diagnosis bug, fixed ─────────────────────────


def test_open_conflict_refuses_the_invalid_type_the_bug_used_to_pass(tmp_path):
    """The root cause, proven directly and permanently (not patch-
    dependent — diagnosis.py's own validation is what made the original
    `type="tribunal-review"` call raise CatalogError, silently swallowed
    by log_to_diagnosis's blanket except): open_conflict has always
    refused this type name, confirming why the old call could never
    have worked."""
    from sovereign_agent.diagnosis import CatalogError, ConflictCatalog

    cat = ConflictCatalog(tmp_path / "diagnosis")
    import pytest

    with pytest.raises(CatalogError, match="tribunal-review"):
        cat.open_conflict(type="tribunal-review", trigger_event="x")


def test_log_to_diagnosis_now_returns_a_real_case(tmp_path):
    import pytest

    from sovereign_agent import tribunal as tribunal_mod

    if not _patched(tribunal_mod.tribunal):
        pytest.skip("pre-apply: tribunal.py log_to_diagnosis not yet patched")
    from sovereign_agent.diagnosis import ConflictCatalog
    from sovereign_agent.tribunal import convene
    from sovereign_agent.tribunal.tribunal import log_to_diagnosis

    verdict = convene({"text": "a small, reversible, well-tested change"},
                      include_kernel=False)
    case_id = log_to_diagnosis({"change": "test change"}, verdict, tmp_path)
    assert case_id is not None
    assert case_id.startswith("TRIB")

    cat = ConflictCatalog(tmp_path / "diagnosis")
    conflict = cat.get_conflict(case_id)
    assert conflict is not None
    assert conflict.type == "ambiguity"
    assert conflict.case_id == case_id


# ─── (b) artisan lens: measured data over prose ──────────────────────────


def test_artisan_unaffected_when_no_measured_data_present():
    from sovereign_agent.spectrum.lenses import artisan

    read = artisan("a plain string proposal with no dict keys at all")
    assert read.lens == "artisan"
    # matches the ORIGINAL heuristic exactly — no measured-data branch taken
    assert read.score <= 0.1 + 1e-9   # no craft words matched in this string...


def test_artisan_overrides_with_measured_quality_score():
    import pytest

    from sovereign_agent.spectrum.lenses import artisan

    if not _patched(artisan):
        pytest.skip("pre-apply: artisan lens not yet patched")
    high = artisan({"quality_score": 95.0, "hardening_critical_ok": True})
    assert high.stance in ("support", "champion")
    assert high.score > 0.5

    low = artisan({"quality_score": 20.0, "hardening_critical_ok": True})
    assert low.stance in ("oppose", "caution")
    assert low.score < 0.0


def test_artisan_critical_failure_forces_a_low_score_regardless_of_number():
    import pytest

    from sovereign_agent.spectrum.lenses import artisan

    if not _patched(artisan):
        pytest.skip("pre-apply: artisan lens not yet patched")
    read = artisan({"quality_score": 99.0, "hardening_critical_ok": False})
    assert read.score <= -0.6
    assert any("critical" in c for c in read.concerns)


def test_artisan_prose_fallback_still_works_with_a_plain_dict():
    import pytest

    from sovereign_agent.spectrum.lenses import artisan

    if not _patched(artisan):
        pytest.skip("pre-apply: artisan lens not yet patched")
    # a dict WITHOUT the measured keys must fall back to prose, unaffected
    read = artisan({"text": "well tested, documented, and clean — no debt"})
    assert read.gifts == ["tested / documented / clean"]


# ─── quality/review.py — the "what to audit standing" logic ─────────────


def test_build_review_proposal_finds_the_newest_applied_module(tmp_path, monkeypatch):
    from sovereign_agent.quality.review import build_review_proposal

    project_root = tmp_path / "project"
    (project_root / "src" / "sovereign_agent").mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    mod_dir = project_root / "aria-something"
    mod_dir.mkdir()
    (mod_dir / "README.md").write_text("# aria-something\n\nreal content here.\n",
                                       encoding="utf-8")
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    import sovereign_agent.quality.review as review_mod

    monkeypatch.setattr(review_mod, "_project_root",
                       lambda src_root: project_root)

    proposal = build_review_proposal(tmp_path / "data")
    assert proposal is not None
    assert "real content here" in proposal["text"]
    assert proposal["change"] == "aria-something"


def test_build_review_proposal_folds_in_the_measured_quality_score(tmp_path, monkeypatch):
    from sovereign_agent.quality import record_quality_pass
    from sovereign_agent.quality.review import build_review_proposal

    project_root = tmp_path / "project"
    mod_dir = project_root / "aria-something"
    mod_dir.mkdir(parents=True)
    (mod_dir / "README.md").write_text("readme text\n", encoding="utf-8")
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    import sovereign_agent.quality.review as review_mod

    monkeypatch.setattr(review_mod, "_project_root",
                       lambda src_root: project_root)

    data_dir = tmp_path / "data"
    good = tmp_path / "good.py"
    good.write_text(
        '"""ok."""\ndef f(a: int) -> int:\n    if a is None: raise ValueError()\n'
        '    emit_event = None\n    return a\n', encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_good.py").write_text('"""tests for good."""\n', encoding="utf-8")
    record_quality_pass([good], data_dir=data_dir)

    proposal = build_review_proposal(data_dir)
    assert "quality_score" in proposal
    assert "hardening_critical_ok" in proposal


def test_build_review_proposal_none_when_nothing_applied_yet(tmp_path, monkeypatch):
    from sovereign_agent.quality.review import build_review_proposal

    empty_root = tmp_path / "empty-project"
    empty_root.mkdir()

    import sovereign_agent.quality.review as review_mod

    monkeypatch.setattr(review_mod, "_project_root",
                       lambda src_root: empty_root)

    assert build_review_proposal(tmp_path / "data") is None


# ─── (c) the standing scan phase ─────────────────────────────────────────


def test_sentinel_standing_phase_logs_a_diagnosis_case(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    if not _patched(QualitySentinel):
        pytest.skip("pre-apply: quality_sentinel.py standing phase not yet patched")

    project_root = tmp_path / "project"
    mod_dir = project_root / "aria-something"
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    payload.mkdir(parents=True)
    (payload / "thing.py").write_text(
        '"""ok."""\ndef f(a: int) -> int:\n    if a is None: raise ValueError()\n'
        '    emit_event = None\n    return a\n', encoding="utf-8")
    (project_root / "tests").mkdir()
    (project_root / "tests" / "test_thing.py").write_text(
        '"""tests for thing."""\n', encoding="utf-8")
    (mod_dir / "README.md").write_text("a real module\n", encoding="utf-8")
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    import sovereign_agent.stewardship.quality_sentinel as qs_mod

    monkeypatch.setattr(qs_mod, "_repo_root", lambda src_root: None)
    monkeypatch.setattr(qs_mod, "_project_root", lambda src_root: project_root)

    data_dir = tmp_path / "data"
    sentinel = QualitySentinel(data_dir)
    sentinel.scan()

    standing = sentinel.load_catalog(name="standing-audit")
    assert standing is not None
    assert standing.get("case_id", "").startswith("TRIB")

    from sovereign_agent.diagnosis import ConflictCatalog

    cat = ConflictCatalog(data_dir / "diagnosis")
    conflict = cat.get_conflict(standing["case_id"])
    assert conflict is not None
    assert conflict.type == "ambiguity"


def test_sentinel_standing_phase_never_breaks_the_scan_on_failure(tmp_path, monkeypatch):
    """Even if the standing-audit phase itself explodes, scan() must still
    return a real report — it's best-effort, never load-bearing for the
    quality pass itself."""
    import pytest

    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    if not _patched(QualitySentinel):
        pytest.skip("pre-apply: quality_sentinel.py standing phase not yet patched")

    import sovereign_agent.quality.review as review_mod

    def _boom(data_dir):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(review_mod, "build_review_proposal", _boom)

    sentinel = QualitySentinel(tmp_path / "data")
    report = sentinel.scan()   # must not raise
    assert report is not None
