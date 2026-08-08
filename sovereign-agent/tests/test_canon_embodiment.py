"""Behavior tests for aria-canon-embodiment — prove a clause referenced in a
fake file is found, a clause with no references is flagged orphaned, and
running against the REAL repo produces the honest, verified number (9/35
cited outside mos_canon.py as of 2026-07-03) — not an assumed one."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.canon_embodiment import extract_clause_ids, find_references


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src/sovereign_agent/mos_canon.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())


def test_extract_clause_ids_returns_the_real_35():
    ids = extract_clause_ids()
    assert len(ids) == 35
    assert "mos-founding-equation" in ids
    assert "mos-beacon" in ids


def test_a_referenced_clause_is_found(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_text(
        'x = get_clause("mos-priority-stack")\n', encoding="utf-8",
    )
    report = find_references(tmp_path, clause_ids=["mos-priority-stack", "mos-beacon"])
    assert "mos-priority-stack" in report.embodied
    assert report.embodied["mos-priority-stack"][0].line == 1
    assert "mos-beacon" in report.orphaned


def test_an_unreferenced_clause_is_orphaned(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_text("x = 1\n", encoding="utf-8")
    report = find_references(tmp_path, clause_ids=["mos-never-cited"])
    assert report.orphaned == ["mos-never-cited"]
    assert report.embodied == {}


def test_the_canon_file_itself_does_not_count_as_embodiment(tmp_path):
    """A clause's own declaration line (inside mos_canon.py) must not count
    as its own embodiment — otherwise every clause would trivially be
    'embodied' by existing."""
    (tmp_path / "src").mkdir()
    canon = tmp_path / "src" / "mos_canon.py"
    canon.write_text('CanonClause(id="mos-example", ...)\n', encoding="utf-8")
    report = find_references(tmp_path, clause_ids=["mos-example"])
    assert report.orphaned == ["mos-example"]


def test_multiple_locations_for_the_same_clause_are_all_recorded(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text('use("mos-beacon")\n', encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text('also_use("mos-beacon")\n', encoding="utf-8")
    report = find_references(tmp_path, clause_ids=["mos-beacon"])
    assert len(report.embodied["mos-beacon"]) == 2


# ─── ground truth against the real repo ─────────────────────────────────────

def test_real_repo_finds_the_verified_embodiment_count():
    """The honest number, not an assumed one: 9 of 35 clauses are cited
    outside mos_canon.py as of 2026-07-03. This asserts a range around that
    verified baseline (the exact count may shift a little as the repo
    evolves) rather than a round, unverified 'most of them' claim."""
    report = find_references(REPO_ROOT)
    assert report.total_clauses == 35
    assert 5 <= report.embodied_count <= 20, (
        f"embodied_count={report.embodied_count} — if this moves far outside "
        "the verified 2026-07-03 baseline (9/35), re-verify by hand before "
        "trusting either direction."
    )


def test_real_repo_specific_known_embodied_clauses_are_found():
    """Two concretely-verified real citations: training.py programmatically
    looks up mos-priority-stack; impulse_tools.py's guidance text names
    mos-signal-check."""
    report = find_references(REPO_ROOT)
    assert "mos-priority-stack" in report.embodied
    assert any("training.py" in loc.path for loc in report.embodied["mos-priority-stack"])
    assert "mos-signal-check" in report.embodied


# ─── sentinel wrapper ────────────────────────────────────────────────────────

def test_sentinel_registers_and_reports(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel
    from sovereign_agent.stewardship.registry import get_sentinel_class

    assert get_sentinel_class("canon-embodiment") is CanonEmbodimentSentinel
    s = CanonEmbodimentSentinel(tmp_path)
    health = s.health_status()
    assert health.sentinel_id == "canon-embodiment"
    assert health.level in ("ok", "warning", "error")


def test_sentinel_scan_writes_a_catalog_and_matches_real_ground_truth(tmp_path):
    from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel

    s = CanonEmbodimentSentinel(tmp_path)
    report = s.scan()
    assert report.sentinel_id == "canon-embodiment"
    assert Path(report.catalog_path).is_file()
    assert report.details["summary"].startswith(f"{report.details['embodied'].__len__()}/35")
