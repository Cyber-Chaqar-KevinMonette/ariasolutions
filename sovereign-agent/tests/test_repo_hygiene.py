"""Tests for repo_hygiene — stray root-level script detection. Mirrors
tests/test_loose_threads_live.py's shape."""
from __future__ import annotations

from pathlib import Path

import pytest


def _write(root: Path, rel: str, text: str = "print('scratch')\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_finds_a_stray_root_script(tmp_path):
    from sovereign_agent.repo_hygiene import scan_repo_root

    _write(tmp_path, "fix_cockpit.py")
    scan = scan_repo_root(tmp_path)
    names = {s.symbol for s in scan.scripts}
    assert "fix_cockpit.py" in names


def test_ignores_scripts_inside_subdirectories(tmp_path):
    """src/, tests/, scripts/, aria-<name>/, archive/ — none should be
    flagged, since the scan is deliberately non-recursive."""
    from sovereign_agent.repo_hygiene import scan_repo_root

    _write(tmp_path, "src/sovereign_agent/foo.py")
    _write(tmp_path, "tests/test_foo.py")
    _write(tmp_path, "scripts/build.py")
    _write(tmp_path, "aria-some-module/payload.py")
    _write(tmp_path, "archive/patch_scripts_2026-07-30/old_fix.py")
    scan = scan_repo_root(tmp_path)
    assert scan.scripts == []


def test_ignores_non_python_root_files(tmp_path):
    from sovereign_agent.repo_hygiene import scan_repo_root

    (tmp_path / "README.md").write_text("# hi\n")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    scan = scan_repo_root(tmp_path)
    assert scan.scripts == []


def test_summary_reflects_count(tmp_path):
    from sovereign_agent.repo_hygiene import scan_repo_root

    assert "no stray" in scan_repo_root(tmp_path).summary()
    _write(tmp_path, "one_off.py")
    assert "1 stray" in scan_repo_root(tmp_path).summary()


def test_ledger_dispositions_silence_scripts_with_reasons(tmp_path):
    from sovereign_agent.loose_threads import DispositionLedger
    from sovereign_agent.repo_hygiene.scanner import StrayScript

    led = DispositionLedger(tmp_path)
    s1 = StrayScript(symbol="fix_cockpit.py", path="/x/fix_cockpit.py",
                     size_bytes=10, modified_at="2026-07-30T00:00:00.000000Z")
    s2 = StrayScript(symbol="patch_edit.py", path="/x/patch_edit.py",
                     size_bytes=10, modified_at="2026-07-30T00:00:00.000000Z")
    assert len(led.undispositioned([s1, s2])) == 2
    led.disposition("fix_cockpit.py", "RETIRED", "moved to archive/patch_scripts_2026-07-30/")
    assert [s.symbol for s in led.undispositioned([s1, s2])] == ["patch_edit.py"]
    with pytest.raises(ValueError):
        led.disposition("patch_edit.py", "ACCEPTED", "")  # no silent suppression


def test_sentinel_registered_and_healthy_cycle(tmp_path):
    from sovereign_agent.stewardship import registry

    assert "repo-hygiene" in registry.registered_ids()
    from sovereign_agent.repo_hygiene.sentinel import RepoHygieneSentinel

    s = RepoHygieneSentinel(data_dir=tmp_path)
    assert s.health_status().level == "ok"  # not yet scanned
    report = s.scan()  # the real repo root — cheap, honest
    assert report.findings_count >= 0
    hs = s.health_status()
    assert hs.level in ("ok", "warning")


def test_scan_is_cached_health_status_does_not_rescan(tmp_path, monkeypatch):
    """The hard caching rule this repo's sentinels all follow: scan() is
    the only thing that walks the filesystem; health_status() only reads
    the persisted catalog."""
    import sovereign_agent.repo_hygiene.sentinel as mod
    from sovereign_agent.repo_hygiene.sentinel import RepoHygieneSentinel

    s = RepoHygieneSentinel(data_dir=tmp_path)
    s.scan()

    calls = []

    def _tripwire(*_a, **_k):
        calls.append(1)
        raise AssertionError("health_status() must not re-scan")

    monkeypatch.setattr(mod, "_repo_root", _tripwire)
    s.health_status()  # should not touch the monkeypatched _repo_root at all
    assert calls == []


def test_proposals_list_each_undispositioned_script(tmp_path):
    from sovereign_agent.repo_hygiene.sentinel import RepoHygieneSentinel

    s = RepoHygieneSentinel(data_dir=tmp_path)
    report = s.scan()
    proposals = s.proposals(report)
    assert len(proposals) == report.findings_count
    if proposals:
        assert proposals[0]["summary"]
        assert proposals[0]["remediation"]
