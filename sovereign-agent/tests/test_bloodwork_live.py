"""Behavior tests for aria-bloodwork, promoted to live tests/ — tests the
REAL, already-patched modules directly. Plain imports, no shadow copy.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


# ─── aegis bootstrap ─────────────────────────────────────────────────────


def test_ensure_aegis_bootstrap_creates_dir_and_key(tmp_path):
    from sovereign_agent.aegis.bootstrap import ensure_aegis_bootstrap

    info = ensure_aegis_bootstrap(tmp_path)
    aegis_dir = Path(info["aegis_dir"])
    assert aegis_dir.is_dir()
    assert info["key_created"] is True
    key = aegis_dir / "conductor.key"
    assert key.is_file()
    assert stat.S_IMODE(os.stat(key).st_mode) == 0o600


def test_ensure_aegis_bootstrap_idempotent(tmp_path):
    from sovereign_agent.aegis.bootstrap import ensure_aegis_bootstrap

    ensure_aegis_bootstrap(tmp_path)
    info2 = ensure_aegis_bootstrap(tmp_path)
    assert info2["key_created"] is False


def test_bootstrap_clears_the_locator_alert(tmp_path):
    """THE point of item (a): after bootstrap, the LocatorSentinel's
    alert-criticality aegis_dir entry stops erroring."""
    from sovereign_agent.aegis.bootstrap import ensure_aegis_bootstrap
    from sovereign_agent.stewardship.locator_sentinel import LocatorSentinel

    s = LocatorSentinel(data_dir=tmp_path)
    s.scan()
    assert s.health_status().level == "error"  # missing aegis dir = alert

    ensure_aegis_bootstrap(tmp_path)
    s.scan()
    assert s.health_status().level != "error"


def test_doctor_check_aegis_registered_and_ok():
    from sovereign_agent.doctor import check_aegis

    result = check_aegis()  # isolated_paths fixture points data_dir at tmp
    assert result.name == "aegis"
    assert result.level == "ok"


# ─── conformance ─────────────────────────────────────────────────────────


def test_kill_switch_rule_scoped_to_src_and_skips_tests(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import KillSwitchDocumentedRule

    # A repo with src/ layout: staged copies + test files must be ignored.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bad_sentinel.py").write_text('"""no switch"""\n')
    (tmp_path / "src" / "test_bad_sentinel.py").write_text('"""test file"""\n')
    (tmp_path / "aria-staged").mkdir()
    (tmp_path / "aria-staged" / "staged_sentinel.py").write_text('"""staged"""\n')

    violations = KillSwitchDocumentedRule().evaluate(tmp_path)
    flagged = {v.path for v in violations}
    assert str(tmp_path / "src" / "bad_sentinel.py") in flagged
    assert len(flagged) == 1  # not the test file, not the staged copy


def test_kill_switch_rule_falls_back_without_src_layout(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import KillSwitchDocumentedRule

    (tmp_path / "plain_sentinel.py").write_text('"""no switch"""\n')
    violations = KillSwitchDocumentedRule().evaluate(tmp_path)
    assert len(violations) == 1


def test_live_tree_has_zero_kill_switch_violations():
    """The actual bloodwork result: the live src/ tree is clean."""
    import sovereign_agent
    from sovereign_agent.stewardship.conformance_sentinel import KillSwitchDocumentedRule

    repo_root = Path(sovereign_agent.__file__).parent.parent.parent
    violations = KillSwitchDocumentedRule().evaluate(repo_root)
    assert violations == [], [v.path for v in violations]


def test_documented_registry_switches_actually_work(monkeypatch, tmp_path):
    """Never document a switch that doesn't work: setting each documented
    env var must actually disable that sentinel via is_enabled()."""
    from sovereign_agent.stewardship import registry

    cases = {
        "godtier": "SOV_NO_GODTIER_SENTINEL",
        "resilience": "SOV_NO_RESILIENCE_SENTINEL",
        "peig": "SOV_NO_PEIG_SENTINEL",
        "tribunal": "SOV_NO_TRIBUNAL_SENTINEL",
        "atoms-compact": "SOV_NO_ATOMS_COMPACT_SENTINEL",
        "schedule": "SOV_NO_SCHEDULE_SENTINEL",
        "cache": "SOV_NO_CACHE_SENTINEL",
        "glyphs": "SOV_NO_GLYPHS_SENTINEL",
    }
    for sid, env in cases.items():
        s = registry.instantiate(sid, tmp_path)
        assert s.is_enabled() is True, sid
        monkeypatch.setenv(env, "1")
        assert s.is_enabled() is False, f"{env} documented but has no effect"
        monkeypatch.delenv(env)
