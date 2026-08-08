"""Tests for god-tier-ratchet-d — the honest measurement fix in
godtier/targets.py. Proves an APPLIED module is scored on its live reality
(not its emptied staging husk), a direct-patch module isn't penalized for
having no payload, and a genuinely-empty skeleton still scores low. This is
measuring truth — the scanner was previously wrong in her disfavor.
"""
from __future__ import annotations

from sovereign_agent.godtier import rubric
from sovereign_agent.godtier.targets import _is_applied, staged_modules


def _mod(repo, name, *, payload=False, tests=False, readme=False, apply=False,
         patch=False, snapshot=False, backups=False, payload_body="x = 1\n"):
    m = repo / name
    m.mkdir()
    if payload:
        p = m / "payload" / "src" / "sovereign_agent" / name.replace("aria-", "").replace("-", "_")
        p.mkdir(parents=True)
        (p / "__init__.py").write_text('"""doc."""\n' + payload_body, encoding="utf-8")
    if tests:
        (m / "tests").mkdir()
        (m / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    if readme:
        (m / "README.md").write_text("# readme\n", encoding="utf-8")
    if apply:
        (m / f"apply_{name.replace('aria-','').replace('-','_')}.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    if patch:
        (m / "patch_thing.py").write_text("# patch\n", encoding="utf-8")
    if snapshot:
        (m / ".safe_apply_snapshot").mkdir()
    if backups:
        (m / "backups").mkdir()
    return m


def _score(repo, name):
    tgt = next(t for t in staged_modules(repo) if t.id == name)
    return rubric.score_target(tgt)


def test_applied_via_live_test_is_detected(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_thing_widget.py").write_text("def test():\n    pass\n", encoding="utf-8")
    m = _mod(tmp_path, "aria-thing-widget", apply=True)  # no payload — applied
    assert _is_applied(m, tmp_path) is True


def test_applied_no_payload_module_scores_god_tier(tmp_path):
    # An applied module (live test present, apply script) with no staging
    # payload must be recognized as the complete, live thing it is.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_thing_widget.py").write_text("def test():\n    pass\n", encoding="utf-8")
    _mod(tmp_path, "aria-thing-widget", apply=True)
    s = _score(tmp_path, "aria-thing-widget")
    assert s["band"] == "god_tier", s


def test_direct_patch_module_not_penalized_for_no_payload(tmp_path):
    # A patch_*.py module legitimately has no payload package.
    _mod(tmp_path, "aria-patchy", apply=True, patch=True, readme=True)
    tgt = next(t for t in staged_modules(tmp_path) if t.id == "aria-patchy")
    assert tgt.signals["has_payload"] is True   # credited as applied
    assert tgt.signals["applied"] is True


def test_empty_skeleton_still_scores_low(tmp_path):
    # No payload, no live test, no apply markers → genuinely incomplete.
    _mod(tmp_path, "aria-ghost")
    s = _score(tmp_path, "aria-ghost")
    assert s["band"] in ("neglected", "weak"), s
    assert _is_applied(tmp_path / "aria-ghost", tmp_path) is False


def test_normal_staged_module_with_payload_unchanged(tmp_path):
    # A real not-yet-applied module with payload + tests + readme + apply
    # scores god-tier on its payload, exactly as before the fix.
    _mod(tmp_path, "aria-fresh", payload=True, tests=True, readme=True, apply=True,
         payload_body="try:\n    x = 1\nexcept Exception:\n    pass\n")
    s = _score(tmp_path, "aria-fresh")
    assert s["band"] == "god_tier", s


def test_promoted_test_credits_a_payload_module(tmp_path):
    # payload present but staging tests were promoted to live tests/ —
    # the promoted test must count (the module IS tested).
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_promoted.py").write_text("def test():\n    pass\n", encoding="utf-8")
    _mod(tmp_path, "aria-promoted", payload=True, readme=True, apply=True,
         payload_body="try:\n    x=1\nexcept Exception:\n    pass\n")
    tgt = next(t for t in staged_modules(tmp_path) if t.id == "aria-promoted")
    assert tgt.signals["has_tests"] is True   # credited via the live test
