"""Tests for skill_sentinel — the steward over Aria's skill library.

The contract under test: the Sentinel reads, ranks, and advises, and never
mutates the library or blocks access.
"""
from __future__ import annotations

from sovereign_agent.skillsmith import SkillLibrary
from sovereign_agent.skill_sentinel import SkillSentinel


def _seed(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.create("Root cause isolation", "Find the cause, not the symptom.",
               domain="technical", breakdown=["observe", "test"], tags=["diagnosis"])
    lib.create("Root-cause discipline", "Cause over symptom, always.",
               domain="technical", breakdown=["observe"], tags=["diagnosis"])
    lib.create("Calibrated patience", "Hold until the signal is earned.",
               domain="moral", breakdown=["pause"], tags=["intuition"])
    return lib, SkillSentinel(lib)


def test_find_returns_matches_with_ids(tmp_path):
    _, sen = _seed(tmp_path)
    hits = sen.find("diagnosis")
    assert hits
    assert all(m.skill_id.startswith("skill-") for m in hits)
    assert all(m.why for m in hits)


def test_context_for_returns_full_bundle(tmp_path):
    lib, sen = _seed(tmp_path)
    sid = lib.all()[0].skill_id
    ctx = sen.context_for(sid)
    assert ctx is not None
    assert set(ctx) >= {"skill_id", "breakdown", "context", "triggers", "tags"}


def test_context_for_unknown_is_none(tmp_path):
    _, sen = _seed(tmp_path)
    assert sen.context_for("skill-nope-000000") is None


def test_brief_is_rendered_text(tmp_path):
    _, sen = _seed(tmp_path)
    out = sen.brief("diagnosis")
    assert "diagnosis" in out and "skill-" in out


def test_duplicates_flags_similar_skills(tmp_path):
    _, sen = _seed(tmp_path)
    dupes = sen.suggest_merges(threshold=0.5)
    # the two near-identical "root cause" skills should cluster
    assert any(len(c.skill_ids) == 2 for c in dupes)


def test_health_report_shape(tmp_path):
    _, sen = _seed(tmp_path)
    h = sen.health()
    assert h["counts"]["active"] == 3
    assert "stale" in h and "duplicate_clusters" in h and "malformed" in h


def test_malformed_detects_bad_skill(tmp_path):
    lib, sen = _seed(tmp_path)
    # write a structurally-broken skill straight to disk
    bad = lib.create("Temp", "t", breakdown=["x"])
    p = tmp_path / f"{bad.skill_id}.json"
    import json
    d = json.loads(p.read_text())
    d["domain"] = "not-a-domain"
    d["breakdown"] = []
    p.write_text(json.dumps(d))
    assert any(m.skill_id == bad.skill_id for m in sen.malformed())


def test_sentinel_never_mutates_library(tmp_path):
    lib, sen = _seed(tmp_path)
    before = {s.skill_id: s.version for s in lib.all()}
    # exercise every read path
    sen.find("x"); sen.brief("x"); sen.duplicates(); sen.suggest_merges()
    sen.stale(days=0); sen.malformed(); sen.health(); sen.tidy_report()
    for s in lib.all():
        sen.context_for(s.skill_id)
    after = {s.skill_id: s.version for s in lib.all()}
    assert before == after  # nothing changed


def test_sentinel_has_no_write_methods():
    # The steward exposes no mutation surface — assists, never gates.
    forbidden = {"create", "enrich", "merge", "archive", "record_use", "delete"}
    assert not (forbidden & set(dir(SkillSentinel)))
