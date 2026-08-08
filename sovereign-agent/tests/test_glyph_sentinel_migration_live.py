"""Behavior tests for aria-glyph-sentinel-migration, promoted to live
tests/ — tests the REAL, already-patched
`sovereign_agent.stewardship.glyph_sentinel` directly, no shadow copy, no
`sys.modules` manipulation. See test_glyph_sentinel_migration.py (staged
only) for the shadow-copy pre-apply verification version.
"""
from __future__ import annotations

from pathlib import Path


def test_glyphs_registered_in_global_sentinel_registry():
    from sovereign_agent.stewardship import registry

    assert "glyphs" in registry.registered_ids()


def test_gather_health_includes_glyphs(tmp_path):
    from sovereign_agent.stewardship import gather_health

    statuses = gather_health(tmp_path / "data")
    assert any(s.sentinel_id == "glyphs" for s in statuses)


def test_id_title_tier(tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    assert gs.id == "glyphs"
    assert "Glyph" in gs.title
    assert gs.tier == 1


def test_articles_nonempty(tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    articles = gs.articles()
    assert len(articles) >= 3


def test_health_status_before_any_scan_is_ok_not_yet_scanned(tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    hs = gs.health_status()
    assert hs.level == "ok"
    assert "not yet scanned" in hs.summary


def test_scan_delegates_to_real_free_functions_and_saves_catalog(tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    report = gs.scan()
    assert report.sentinel_id == "glyphs"
    assert report.findings_count >= 0
    assert Path(report.catalog_path).exists()


def test_health_status_after_scan_reads_cache_not_a_fresh_scan(tmp_path, monkeypatch):
    from sovereign_agent.stewardship import glyph_sentinel as gs_module

    gs = gs_module.GlyphSentinel(data_dir=tmp_path / "data")
    gs.scan()

    def _boom(*a, **kw):
        raise AssertionError("health_status() must not re-scan — it should read the cache")

    monkeypatch.setattr(gs_module, "scan_source_tree", _boom)
    hs = gs.health_status()
    assert hs.level in ("ok", "warning", "error")


def test_proposals_and_coverage_gaps_read_from_report_details(tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    report = gs.scan()
    props = gs.proposals(report)
    gaps = gs.coverage_gaps(report)
    assert len(props) == len(report.details.get("proposals", []))
    assert len(gaps) == len(report.details.get("coverage_gaps", []))


def test_legacy_free_functions_still_importable_and_unchanged():
    from sovereign_agent.stewardship import glyph_sentinel

    for name in (
        "scan_source_tree", "find_source_root", "load_catalog", "save_catalog",
        "catalog_path", "generate_proposals", "detect_coverage_gaps",
    ):
        assert hasattr(glyph_sentinel, name)


def test_legacy_call_sites_still_import_cleanly():
    import sovereign_agent.doctor  # noqa: F401
    import sovereign_agent.cli  # noqa: F401
    import sovereign_agent.workflow.catalog  # noqa: F401
    import sovereign_agent.cockpit.cosmic_fitness  # noqa: F401
