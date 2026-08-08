"""aria-quality-sentinel — the persisted quality ledger + standing sentinel.
(Quality round · Q1)

Pre-apply, patch-dependent behavior (stewardship/__init__.py registration,
cockpit/app.py worker-latch persistence) skips with a written reason; the
apply script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect
import json
import textwrap


def _patched(obj) -> bool:
    return "quality-sentinel-d" in inspect.getsource(obj)


# ─── quality/ledger.py — the persisted score ─────────────────────────────


def _write_good_module(path):
    path.write_text(textwrap.dedent('''
        """A tiny, well-behaved module."""
        from __future__ import annotations


        def add(a: int, b: int) -> int:
            if not isinstance(a, int) or not isinstance(b, int):
                raise ValueError("a and b must be int")
            return a + b
    '''), encoding="utf-8")


def _write_bad_module(path):
    path.write_text(textwrap.dedent('''
        def risky(x):
            try:
                return 1 / x
            except:
                pass
    '''), encoding="utf-8")


def test_record_quality_pass_scores_and_persists(tmp_path):
    from sovereign_agent.quality import latest_quality, record_quality_pass

    mod = tmp_path / "good_mod.py"
    _write_good_module(mod)
    data_dir = tmp_path / "data"

    result = record_quality_pass([mod], data_dir=data_dir)
    assert len(result.files) == 1
    assert result.files[0].value > 0

    stored = latest_quality(data_dir=data_dir)
    assert stored is not None
    assert stored["pass_id"] == result.pass_id
    assert stored["files"][0]["path"] == str(mod)


def test_bad_file_never_hides_in_the_average(tmp_path):
    from sovereign_agent.quality import record_quality_pass

    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    _write_good_module(good)
    _write_bad_module(bad)
    data_dir = tmp_path / "data"

    result = record_quality_pass([good, bad], data_dir=data_dir)
    assert len(result.files) == 2
    # a pass is critical_ok only if EVERY file is — one bad file fails it all
    assert result.critical_ok is False
    bad_entry = next(f for f in result.files if f.path == str(bad))
    assert bad_entry.critical_ok is False
    assert bad_entry.failures   # names the failing checks


def test_critical_failures_is_a_strict_subset_of_all_failures(tmp_path):
    """Regression: gate.py's BLOCK message once used `failures` (ALL
    failing checks, any weight) to explain a critical failure, wrongly
    labeling non-critical gaps (e.g. typed_signatures, weight 4) as
    'critical'. `critical_failures` must contain only weight-≥8 labels."""
    from sovereign_agent.qa.hardening import harden_module
    from sovereign_agent.quality import record_quality_pass

    bad = tmp_path / "bad.py"
    _write_bad_module(bad)
    result = record_quality_pass([bad], data_dir=tmp_path / "data")
    entry = result.files[0]

    report = harden_module(bad)
    critical_labels = {c.label for c in report.failures() if c.weight >= 8}
    assert set(entry.critical_failures) == critical_labels
    assert set(entry.critical_failures).issubset(set(entry.failures))


def test_missing_or_unparseable_targets_are_skipped_not_crashed(tmp_path):
    from sovereign_agent.quality import record_quality_pass

    missing = tmp_path / "does_not_exist.py"
    syntax_error = tmp_path / "broken.py"
    syntax_error.write_text("def f(:\n", encoding="utf-8")
    good = tmp_path / "good.py"
    _write_good_module(good)
    data_dir = tmp_path / "data"

    result = record_quality_pass([missing, syntax_error, good], data_dir=data_dir)
    assert len(result.files) == 1   # only the good one scored
    assert result.files[0].path == str(good)


def test_empty_pass_is_honest_not_a_critical_failure(tmp_path):
    """Regression: 'nothing was scored' and 'everything failed' must never
    look the same. An empty pass (no targets found) is vacuously
    critical_ok — caught live when the sentinel's fallback found 0 files
    and the pass was wrongly reported as a critical failure."""
    from sovereign_agent.quality import record_quality_pass

    result = record_quality_pass([], data_dir=tmp_path / "data")
    assert result.files == []
    assert result.critical_ok is True


def test_quality_trend_from_stored_scores_only(tmp_path):
    from sovereign_agent.quality import quality_trend, record_quality_pass

    data_dir = tmp_path / "data"
    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    _write_good_module(good)
    _write_bad_module(bad)

    assert quality_trend(data_dir=data_dir) == "insufficient-history"
    record_quality_pass([good], data_dir=data_dir)          # high score
    record_quality_pass([good, bad], data_dir=data_dir)     # dragged down
    trend = quality_trend(data_dir=data_dir)
    assert trend == "declining"


def test_corrupt_ledger_lines_never_wedge_a_read(tmp_path):
    from sovereign_agent.quality import latest_quality, record_quality_pass

    data_dir = tmp_path / "data"
    good = tmp_path / "good.py"
    _write_good_module(good)
    record_quality_pass([good], data_dir=data_dir)

    ledger = data_dir / "quality" / "ledger.ndjson"
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")

    assert latest_quality(data_dir=data_dir) is not None


# ─── stewardship/quality_sentinel.py — the standing sentinel ─────────────


def test_sentinel_registered():
    import sovereign_agent.stewardship.quality_sentinel  # noqa: F401
    from sovereign_agent.stewardship import registry

    assert "quality" in registry.registered_ids()


def test_sentinel_scan_scores_the_newest_applied_module(tmp_path, monkeypatch):
    """On a fresh install (no bookmark, no git repo reachable in the tmp
    sandbox), the sentinel falls back to the newest .applied_ok module's
    payload files — something real to score, not nothing."""
    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    repo_root = tmp_path / "repo"
    mod_dir = repo_root / "aria-something"
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    payload.mkdir(parents=True)
    _write_good_module(payload / "thing.py")
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    monkeypatch.setattr(
        "sovereign_agent.stewardship.quality_sentinel._repo_root",
        lambda src_root: None)   # force the fallback path, not git-diff
    monkeypatch.setattr(
        "sovereign_agent.stewardship.quality_sentinel._project_root",
        lambda src_root: repo_root)

    data_dir = tmp_path / "data"
    sentinel = QualitySentinel(data_dir)
    report = sentinel.scan()
    assert report.details["files_scanned"] == 1
    assert report.details["pass"]["files"][0]["path"].endswith("thing.py")


def test_sentinel_health_reflects_critical_failure(tmp_path, monkeypatch):
    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    repo_root = tmp_path / "repo"
    mod_dir = repo_root / "aria-bad-thing"
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    payload.mkdir(parents=True)
    _write_bad_module(payload / "bad.py")
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    monkeypatch.setattr(
        "sovereign_agent.stewardship.quality_sentinel._repo_root",
        lambda src_root: None)   # force the fallback path, not git-diff
    monkeypatch.setattr(
        "sovereign_agent.stewardship.quality_sentinel._project_root",
        lambda src_root: repo_root)

    data_dir = tmp_path / "data"
    sentinel = QualitySentinel(data_dir)
    sentinel.scan()
    health = sentinel.health_status()
    assert health.level == "warning"


def test_sentinel_proposals_never_repair_only_propose(tmp_path, monkeypatch):
    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    repo_root = tmp_path / "repo"
    mod_dir = repo_root / "aria-bad-thing"
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    payload.mkdir(parents=True)
    bad_file = payload / "bad.py"
    _write_bad_module(bad_file)
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    monkeypatch.setattr(
        "sovereign_agent.stewardship.quality_sentinel._repo_root",
        lambda src_root: None)   # force the fallback path, not git-diff
    monkeypatch.setattr(
        "sovereign_agent.stewardship.quality_sentinel._project_root",
        lambda src_root: repo_root)

    data_dir = tmp_path / "data"
    sentinel = QualitySentinel(data_dir)
    report = sentinel.scan()
    proposals = sentinel.proposals(report)
    assert proposals and all(p["remediation"] for p in proposals)
    assert bad_file.exists()   # nothing was touched — propose only


def test_sentinel_kill_switch(tmp_path, monkeypatch):
    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    monkeypatch.setenv("SOV_NO_QUALITY_SENTINEL", "1")
    assert not QualitySentinel(tmp_path).is_enabled()


def test_project_root_differs_from_git_root_in_a_nested_repo(tmp_path):
    """Regression, caught live: this project (sovereign-agent/) is nested
    inside a larger git checkout (AA-Erebo/) — `git rev-parse
    --show-toplevel` returns the OUTER root, but aria-*/ staged folders and
    pyproject.toml live at the INNER project root. Using the git root for
    the aria-*/ fallback glob silently found zero files (not an error —
    the exact kind of quiet failure this sentinel exists to catch
    elsewhere). `_project_root` must walk up to pyproject.toml instead."""
    from sovereign_agent.stewardship.quality_sentinel import _project_root

    outer = tmp_path / "outer-checkout"
    inner = outer / "nested-project"
    src_root = inner / "src" / "sovereign_agent"
    src_root.mkdir(parents=True)
    (inner / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    # the outer checkout has its OWN unrelated pyproject.toml further up —
    # if the walk-up stopped at the wrong one, this would misresolve too
    (outer / "pyproject.toml").write_text("[project]\nname='outer'\n", encoding="utf-8")

    found = _project_root(src_root)
    assert found == inner   # the nearest ancestor, not the outer one


def test_newest_applied_module_fallback_uses_project_root_not_git_root(tmp_path):
    """End-to-end version of the bug: scan() must find aria-*/.applied_ok
    folders under the PROJECT root even when git's top-level is a
    different (outer) directory."""
    from sovereign_agent.stewardship.quality_sentinel import QualitySentinel

    outer_git_root = tmp_path / "outer"
    project_root = tmp_path / "outer" / "inner-project"
    mod_dir = project_root / "aria-something"
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    payload.mkdir(parents=True)
    _write_good_module(payload / "thing.py")
    (mod_dir / ".applied_ok").write_text("2026-01-01T00:00:00Z\n", encoding="utf-8")

    import sovereign_agent.stewardship.quality_sentinel as qs_mod

    monkeypatch_repo_root = outer_git_root   # git says the OUTER dir is top-level
    orig_repo_root = qs_mod._repo_root
    orig_project_root = qs_mod._project_root
    try:
        qs_mod._repo_root = lambda src_root: monkeypatch_repo_root
        qs_mod._project_root = lambda src_root: project_root
        sentinel = QualitySentinel(tmp_path / "data")
        report = sentinel.scan()
        assert report.details["files_scanned"] == 1
    finally:
        qs_mod._repo_root = orig_repo_root
        qs_mod._project_root = orig_project_root


# ─── the patched surfaces (post-apply) ────────────────────────────────────


def test_worker_latch_persists_across_a_cockpit_restart(tmp_path):
    import pytest

    from sovereign_agent.cockpit import app as app_mod

    if not _patched(app_mod):
        pytest.skip("pre-apply: cockpit/app.py worker-latch not yet patched")

    class _Fake:
        def __init__(self):
            from sovereign_agent.config import SETTINGS

            self._settings = SETTINGS

    fake = _Fake()
    app_mod.CockpitApp._persist_worker_latch(fake, "heart")
    from sovereign_agent.config import SETTINGS

    path = SETTINGS.paths.data_dir / "cockpit" / "worker_health.json"
    assert path.exists()
    state = json.loads(path.read_text(encoding="utf-8"))
    assert "heart" in state


def test_criteria_doc_no_longer_says_gap():
    """GOD_TIER_CRITERIA.md's worker-supervision line was stale (the gap
    was already closed by aria-worker-watch, pre-dating this round) —
    confirm the doc sync landed."""
    import pathlib

    import pytest

    import sovereign_agent

    repo_root = pathlib.Path(sovereign_agent.__file__).parents[2]
    text = (repo_root / "GOD_TIER_CRITERIA.md").read_text(encoding="utf-8")
    if "worker-watch-d" not in text:
        pytest.skip("pre-apply: GOD_TIER_CRITERIA.md not yet patched")
    assert "Worker supervision / self-restart. **MET**" in text
