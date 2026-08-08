"""Tests for cockpit-hardening-d — the actual cause of a hung cockpit
(diagnosed live via py-spy, 2026-07-20): CanonEmbodimentSentinel.health_status()
re-ran a ~1,440-file repo walk on every 5s health tick with zero caching.
Fixed to match glyph_sentinel.py's own already-proven cached-catalog
pattern. The backups/ exclusion in find_references() is kept as
additional, harmless hardening (see its own comment for why it wasn't
actually the bottleneck)."""
from __future__ import annotations

from unittest.mock import patch

from sovereign_agent.canon_embodiment.mapper import EXCLUDE_DIRS, find_references


# ── find_references() — the additional hardening ───────────────────────

def test_backups_directory_is_excluded_even_without_bak_suffix(tmp_path):
    """A real full-file backup copy (no .bak suffix) under a backups/ dir
    must not be scanned -- defense in depth even though today's actual
    apply-script backups are already .bak-suffixed and excluded anyway."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "live.py").write_text(
        'x = get_clause("mos-example")\n', encoding="utf-8",
    )
    backups = tmp_path / "aria-something" / "backups" / "20260720_000000"
    backups.mkdir(parents=True)
    (backups / "live.py").write_text(
        'x = get_clause("mos-example")\ny = get_clause("mos-only-in-backup")\n',
        encoding="utf-8",
    )
    report = find_references(tmp_path, clause_ids=["mos-example", "mos-only-in-backup"])
    assert "mos-example" in report.embodied
    assert len(report.embodied["mos-example"]) == 1  # only the live copy, not the backup
    assert "mos-only-in-backup" in report.orphaned  # exists ONLY in backups/ -- must not count


def test_exclude_dirs_matches_glyph_sentinels_convention():
    # glyph_sentinel.py's EXCLUDE_DIRS is a local var inside scan_source_tree(),
    # not importable -- comparing against its known literal set instead.
    glyph_excludes = {".venv", "venv", "__pycache__", "Archive", "dist", "build",
                     ".git", "node_modules", "history"}
    assert glyph_excludes <= EXCLUDE_DIRS
    assert "backups" in EXCLUDE_DIRS


# ── CanonEmbodimentSentinel.health_status() — the actual fix ───────────

def test_health_status_does_not_scan_when_no_catalog_exists(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel

    s = CanonEmbodimentSentinel(tmp_path)
    with patch("sovereign_agent.canon_embodiment.sentinel.find_references") as mock_scan:
        health = s.health_status()
    mock_scan.assert_not_called()
    assert health.level == "ok"
    assert "not yet scanned" in health.summary


def test_health_status_reads_cached_catalog_never_rescans(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel

    s = CanonEmbodimentSentinel(tmp_path)
    # Populate the cache the same way scan() does, without calling scan()
    # itself (which would do the real repo walk) -- isolates the test to
    # health_status()'s own read-cache behavior.
    import json
    catalog_path = s._catalog_path()
    catalog_path.write_text(json.dumps({
        "summary": "1/2 clauses cited outside mos_canon.py · 1 orphaned",
        "embodied": {"mos-a": [{"path": "x.py", "line": 1, "excerpt": "..."}]},
        "orphaned": ["mos-b"],
    }), encoding="utf-8")

    with patch("sovereign_agent.canon_embodiment.sentinel.find_references") as mock_scan:
        health = s.health_status()
    mock_scan.assert_not_called()
    assert health.level == "warning"
    assert "1/2" in health.summary


def test_health_status_all_cited_is_ok(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel
    import json

    s = CanonEmbodimentSentinel(tmp_path)
    s._catalog_path().write_text(json.dumps({
        "embodied": {"mos-a": [{"path": "x.py", "line": 1, "excerpt": "..."}]},
        "orphaned": [],
    }), encoding="utf-8")
    health = s.health_status()
    assert health.level == "ok"
    assert "all clauses cited" in health.summary


def test_health_status_zero_embodied_is_error(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel
    import json

    s = CanonEmbodimentSentinel(tmp_path)
    s._catalog_path().write_text(json.dumps({
        "embodied": {}, "orphaned": ["mos-a", "mos-b"],
    }), encoding="utf-8")
    health = s.health_status()
    assert health.level == "error"


def test_health_status_degrades_gracefully_on_corrupt_catalog(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel

    s = CanonEmbodimentSentinel(tmp_path)
    s._catalog_path().write_text("{not json", encoding="utf-8")
    health = s.health_status()  # must not raise
    assert health.level == "ok"
    assert "unreadable" in health.summary


def test_scan_still_does_the_real_walk_and_populates_the_cache(tmp_path):
    """scan() is the ONLY thing that should still call find_references --
    confirms the split, not just health_status()'s half of it."""
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel

    s = CanonEmbodimentSentinel(tmp_path)
    report = s.scan()
    assert report.catalog_path == str(s._catalog_path())
    assert s._catalog_path().is_file()
    # Now health_status() should read exactly what scan() just wrote.
    with patch("sovereign_agent.canon_embodiment.sentinel.find_references") as mock_scan:
        s.health_status()
    mock_scan.assert_not_called()


# ── ConformanceSentinel — the second instance of the identical bug ─────

def test_conformance_health_status_does_not_scan_when_no_catalog(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import ConformanceSentinel

    s = ConformanceSentinel(tmp_path, rules=[], repo_root=tmp_path)
    with patch.object(s, "scan") as mock_scan:
        health = s.health_status()
    mock_scan.assert_not_called()
    assert health.level == "ok"
    assert "not yet scanned" in health.summary


def test_conformance_health_status_reads_cached_catalog_never_rescans(tmp_path):
    import json

    from sovereign_agent.stewardship.conformance_sentinel import ConformanceSentinel

    s = ConformanceSentinel(tmp_path, rules=[], repo_root=tmp_path)
    cat_path = s.sentinel_dir / "catalogs" / "violations.json"
    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps({
        "violations": [
            {"rule_name": "no-vague-name", "severity": "warning", "surface": "naming",
             "summary": "x", "detail": ""},
        ],
    }), encoding="utf-8")

    with patch.object(s, "scan") as mock_scan:
        health = s.health_status()
    mock_scan.assert_not_called()
    assert health.level == "warning"
    assert "1 warning-level" in health.summary


def test_conformance_health_status_degrades_gracefully_on_corrupt_catalog(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import ConformanceSentinel

    s = ConformanceSentinel(tmp_path, rules=[], repo_root=tmp_path)
    cat_path = s.sentinel_dir / "catalogs" / "violations.json"
    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text("{not json", encoding="utf-8")
    health = s.health_status()  # must not raise
    assert health.level == "ok"
    assert "unreadable" in health.summary


def test_conformance_scan_still_populates_cache_that_health_status_reads(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import ConformanceSentinel

    s = ConformanceSentinel(tmp_path, rules=[], repo_root=tmp_path)
    s.scan()  # empty rules -> 0 violations, but the catalog file must exist
    with patch.object(s, "scan") as mock_scan:
        health = s.health_status()
    mock_scan.assert_not_called()
    assert health.level == "ok"
    assert health.summary == "no conformance violations"


def test_no_vague_name_rule_excludes_backups_directory(tmp_path):
    from sovereign_agent.stewardship.conformance_sentinel import NoVagueNameRule

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "clean.py").write_text("count = 1\n", encoding="utf-8")
    backups = tmp_path / "aria-x" / "backups" / "20260720_000000"
    backups.mkdir(parents=True)
    (backups / "old.py").write_text("data = 1\n", encoding="utf-8")  # vague name, but in backups/

    rule = NoVagueNameRule()
    violations = rule.evaluate(tmp_path)
    assert violations == []  # the only vague name that exists is inside backups/
