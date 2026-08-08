"""Tests for the self-training protocol (the Cosmic-Gym seed)."""
from __future__ import annotations

import json

from sovereign_agent import training as T
from sovereign_agent.intuition import IntuitionEngine, IntuitionForm


def test_audits_pass_on_a_healthy_tree():
    report = T.run_training()
    # every real invariant check should pass on a healthy build
    assert report.audit_passed == report.audit_total
    assert report.audit_total >= 5
    assert report.grade in ("STRONG", "READY")


def test_run_seeds_calibration_reps():
    eng = IntuitionEngine()
    assert "No calibrated domains" in eng.reflect()      # empty at first
    T.run_training(eng)
    rep = eng.domain_report()
    assert rep, "training should have created calibrated domains"
    # study reps should have produced trustworthy pattern/reasoning domains
    assert any(d["reps"] > 0 for d in rep)
    assert "No calibrated domains" not in eng.reflect()


def test_report_structure_and_markdown():
    report = T.run_training()
    d = report.to_dict()
    assert set(d) >= {"audit", "study", "grade", "results", "domains", "reflection"}
    assert d["audit"]["total"] >= 5
    md = T._report_md(report)
    assert "Cosmic-Gym training report" in md
    assert "Audit drills" in md and "Study reps" in md


def test_accumulates_across_runs(tmp_path):
    seed = tmp_path / "intuition_state.json"
    T.run_training(persist_path=seed)
    first = json.loads(seed.read_text())
    reps_first = sum(dom["reps"] for dom in first["domains"])
    # restore + run again → reps grow (fattening)
    eng = IntuitionEngine.restore(first)
    T.run_training(eng, persist_path=seed)
    second = json.loads(seed.read_text())
    reps_second = sum(dom["reps"] for dom in second["domains"])
    assert reps_second > reps_first


def test_seed_from_fresh_writes_snapshot(tmp_path):
    seed = tmp_path / "seed.json"
    report = T.seed_from_fresh(seed)
    assert seed.exists()
    assert report.audit_passed == report.audit_total
    snap = json.loads(seed.read_text())
    assert snap["domains"], "seed should contain calibrated domains"


def test_report_files_and_catalog_written(tmp_path):
    out = tmp_path / "training"
    T.run_training(report_dir=out)
    runs = sorted(out.glob("*/report.json"))
    assert len(runs) == 1
    assert (runs[0].parent / "report.md").exists()
    catalog = json.loads((out / "catalog.json").read_text())
    assert catalog["count"] == 1
    assert catalog["runs"][0]["grade"] in ("STRONG", "READY", "NEEDS ATTENTION")


def test_a_broken_drill_never_crashes_the_run(monkeypatch):
    def boom():
        raise RuntimeError("kaboom")
    bad = T.Drill("audit-bad", "audit", IntuitionForm.TECHNICAL, "self-knowledge:test",
                  "a drill that explodes", 0.5, boom)
    monkeypatch.setattr(T, "_AUDIT_DRILLS", T._AUDIT_DRILLS + [bad])
    report = T.run_training()                      # must not raise
    bad_res = [r for r in report.results if r.id == "audit-bad"]
    assert bad_res and bad_res[0].passed is False
    assert report.grade == "NEEDS ATTENTION"       # a failed audit is surfaced
    assert any("kaboom" in n for n in report.notes)
