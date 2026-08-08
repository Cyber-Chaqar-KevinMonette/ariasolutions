"""Tests for skillsmith — Aria's own skill system.

The load-bearing test here is the kernel guard: a skill is knowledge, never a
backdoor to a deferred-unsafe capability.
"""
from __future__ import annotations

import pytest

from sovereign_agent.skillsmith import (
    DOMAINS, MATURITY_LADDER, SkillLibrary, SkillError, kernel_conflict, new_skill_id,
)


def test_create_and_get_roundtrip(tmp_path):
    lib = SkillLibrary(tmp_path)
    s = lib.create("Root-cause isolation", "Separate symptom from cause.",
                   domain="technical", breakdown=["state symptom", "form hypotheses"],
                   context="Use at the start of any diagnosis.", tags=["diagnosis"])
    assert s.skill_id.startswith("skill-")
    assert s.well_formed() == []
    again = lib.get(s.skill_id)
    assert again is not None and again.name == s.name
    assert again.breakdown == ["state symptom", "form hypotheses"]


def test_ids_are_unique_for_same_name():
    a = new_skill_id("same name")
    b = new_skill_id("same name")
    assert a != b


def test_maturity_rises_with_reps_but_is_bounded(tmp_path):
    lib = SkillLibrary(tmp_path)
    s = lib.create("X", "y", breakdown=["z"])
    assert s.maturity == "seedling"
    for _ in range(3):
        lib.record_use(s.skill_id)
    assert lib.get(s.skill_id).maturity == "practiced"
    for _ in range(30):
        lib.record_use(s.skill_id)
    # capped at the top rung — never escalates past the ladder
    assert lib.get(s.skill_id).maturity == MATURITY_LADDER[-1] == "mastered"


def test_enrich_bumps_version(tmp_path):
    lib = SkillLibrary(tmp_path)
    s = lib.create("X", "y", breakdown=["a"])
    assert s.version == 1
    lib.enrich(s.skill_id, add_breakdown=["b"], add_tags=["t"], note="grew it")
    out = lib.get(s.skill_id)
    assert out.version == 2 and "b" in out.breakdown and "t" in out.tags


def test_merge_preserves_lineage_and_unions_breakdown(tmp_path):
    lib = SkillLibrary(tmp_path)
    a = lib.create("A", "a", breakdown=["one", "two"])
    b = lib.create("B", "b", breakdown=["two", "three"])
    m = lib.merge([a.skill_id, b.skill_id], name="Merged", summary="m")
    assert m.lineage == [a.skill_id, b.skill_id]
    assert m.breakdown == ["one", "two", "three"]  # deduped, order preserved


def test_learn_from_returns_bundle_without_mutating(tmp_path):
    lib = SkillLibrary(tmp_path)
    s = lib.create("A", "a", breakdown=["one"], context="ctx")
    before = lib.get(s.skill_id).version
    bundle = lib.learn_from(s.skill_id)
    assert bundle["breakdown"] == ["one"] and bundle["context"] == "ctx"
    assert lib.get(s.skill_id).version == before  # unchanged


def test_search_ranks_by_relevance(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.create("Diagnosis discipline", "diagnosis diagnosis", breakdown=["x"], tags=["diagnosis"])
    lib.create("Cooking", "unrelated", breakdown=["y"])
    hits = lib.search("diagnosis")
    assert hits and hits[0].name == "Diagnosis discipline"


def test_archive_hides_from_active(tmp_path):
    lib = SkillLibrary(tmp_path)
    s = lib.create("A", "a", breakdown=["x"])
    lib.archive(s.skill_id)
    assert all(x.skill_id != s.skill_id for x in lib.all())
    assert any(x.skill_id == s.skill_id for x in lib.all(include_archived=True))


@pytest.mark.parametrize("name,summary,breakdown", [
    ("Ascend", "Rewrite her own source code.", ["edit code"]),
    ("Self-author", "Redefine her own values at will.", ["edit values"]),
    ("Unbound", "Enable unbounded self-improvement.", ["grow forever"]),
    ("Recurse", "Recursive self-improvement of her weights.", ["x"]),
    ("Escape", "Achieve substrate independence.", ["x"]),
    ("Silence", "Disable the kill switch when inconvenient.", ["x"]),
])
def test_kernel_guard_refuses_unsafe_skills(tmp_path, name, summary, breakdown):
    lib = SkillLibrary(tmp_path)
    with pytest.raises(SkillError):
        lib.create(name, summary, breakdown=breakdown)


def test_kernel_conflict_helper_flags_and_clears():
    assert kernel_conflict("rewrite her own code") is not None
    assert kernel_conflict("a calm, ordinary playbook for writing READMEs") is None


def test_create_rejects_unknown_domain(tmp_path):
    lib = SkillLibrary(tmp_path)
    s = lib.create("X", "y", domain="not-a-domain", breakdown=["z"])
    # creation doesn't hard-fail on domain, but well_formed flags it
    assert any("domain" in p for p in s.well_formed())
    # and the valid set is what we expect
    assert "technical" in DOMAINS and "general" in DOMAINS


def test_corrupt_file_is_skipped_not_fatal(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.create("Good", "g", breakdown=["x"])
    (tmp_path / "skill-broken-000000.json").write_text("{not json", encoding="utf-8")
    # all() must still return the good skill and not raise
    names = [s.name for s in lib.all()]
    assert "Good" in names
