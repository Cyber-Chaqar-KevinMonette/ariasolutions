"""Behavior tests for aria-glyph-sentinel-migration — prove the patched
GlyphSentinel class actually works, using a shadow copy of the whole
package (never touches real src/). STAGED ONLY: never promoted — see
test_glyph_sentinel_migration_live.py for the promoted copy."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "stewardship" / "glyph_sentinel.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-glyph-sentinel-migration" / "patcher.py").is_file():
            return candidate / "aria-glyph-sentinel-migration"
    raise RuntimeError("could not locate aria-glyph-sentinel-migration/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_glyph_sentinel, patch_stewardship_init

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    glyph_py = shadow / "sovereign_agent" / "stewardship" / "glyph_sentinel.py"
    patched, _ = patch_glyph_sentinel(glyph_py.read_text(encoding="utf-8"))
    glyph_py.write_text(patched, encoding="utf-8")

    init_py = shadow / "sovereign_agent" / "stewardship" / "__init__.py"
    patched_init, _ = patch_stewardship_init(init_py.read_text(encoding="utf-8"))
    init_py.write_text(patched_init, encoding="utf-8")

    return shadow


@pytest.fixture
def shadow_pkg(tmp_path, monkeypatch):
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent
        yield sovereign_agent
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


# ── registration ──────────────────────────────────────────────────────────


def test_glyphs_registered_in_global_sentinel_registry(shadow_pkg):
    from sovereign_agent.stewardship import registry

    assert "glyphs" in registry.registered_ids()


def test_gather_health_includes_glyphs(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship import gather_health

    statuses = gather_health(tmp_path / "data")
    assert any(s.sentinel_id == "glyphs" for s in statuses)


# ── GlyphSentinel contract ────────────────────────────────────────────────


def test_id_title_tier(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    assert gs.id == "glyphs"
    assert "Glyph" in gs.title
    assert gs.tier == 1


def test_articles_nonempty(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    articles = gs.articles()
    assert len(articles) >= 3
    assert all(isinstance(a, str) and a for a in articles)


def test_health_status_before_any_scan_is_ok_not_yet_scanned(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    hs = gs.health_status()
    assert hs.level == "ok"
    assert "not yet scanned" in hs.summary


def test_scan_delegates_to_real_free_functions_and_saves_catalog(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    report = gs.scan()
    assert report.sentinel_id == "glyphs"
    assert report.findings_count >= 0
    assert report.catalog_path
    assert Path(report.catalog_path).exists()


def test_health_status_after_scan_reads_cache_not_a_fresh_scan(shadow_pkg, tmp_path, monkeypatch):
    """The critical regression guard: once a scan has populated the cache,
    health_status() must read it back WITHOUT calling scan_source_tree()
    again — proven here by making a second scan_source_tree() call raise."""
    from sovereign_agent.stewardship import glyph_sentinel as gs_module

    gs = gs_module.GlyphSentinel(data_dir=tmp_path / "data")
    gs.scan()

    def _boom(*a, **kw):
        raise AssertionError("health_status() must not re-scan — it should read the cache")

    monkeypatch.setattr(gs_module, "scan_source_tree", _boom)
    hs = gs.health_status()
    assert hs.level in ("ok", "warning", "error")


def test_health_status_reflects_findings_count(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    report = gs.scan()
    hs = gs.health_status()
    if report.findings_count == 0:
        assert hs.level == "ok"
    else:
        assert hs.level == "warning"


def test_proposals_and_coverage_gaps_read_from_report_details(shadow_pkg, tmp_path):
    from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel

    gs = GlyphSentinel(data_dir=tmp_path / "data")
    report = gs.scan()
    props = gs.proposals(report)
    gaps = gs.coverage_gaps(report)
    assert isinstance(props, list)
    assert isinstance(gaps, list)
    assert len(props) == len(report.details.get("proposals", []))
    assert len(gaps) == len(report.details.get("coverage_gaps", []))


# ── legacy free-function surface stays completely untouched ──────────────


def test_legacy_free_functions_still_importable_and_unchanged(shadow_pkg):
    from sovereign_agent.stewardship import glyph_sentinel

    for name in (
        "scan_source_tree", "find_source_root", "load_catalog", "save_catalog",
        "catalog_path", "generate_proposals", "detect_coverage_gaps",
    ):
        assert hasattr(glyph_sentinel, name)


def test_legacy_call_sites_still_import_cleanly(shadow_pkg):
    """doctor.py, cli.py, workflow/catalog.py, cosmic_fitness.py all import
    glyph_sentinel's free functions directly — confirm none of them break."""
    import sovereign_agent.doctor  # noqa: F401
    import sovereign_agent.cli  # noqa: F401
    import sovereign_agent.workflow.catalog  # noqa: F401
    import sovereign_agent.cockpit.cosmic_fitness  # noqa: F401
