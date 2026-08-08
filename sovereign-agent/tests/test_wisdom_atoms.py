"""Tests for M83 wisdom atoms seeding script.

Verifies: atom count, all PATTERN kind, claim length, confidence ranges,
evidence_refs, tags, unique titles, idempotency, and thematic completeness.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    """Robust to running from either the staged location (aria-wisdom-atoms/
    tests/) or the promoted live location (tests/), which differ in nesting
    depth — the exact path-depth bug class fixed elsewhere this session
    (test_tools_all_export_fix.py, test_scanner_tier_a.py, test_command_menu.py)."""
    for candidate in (start, *start.parents):
        if (candidate / "aria-wisdom-atoms" / "payload" / "scripts" / "wisdom_atoms.py").is_file():
            return candidate / "aria-wisdom-atoms"
    raise RuntimeError("could not locate aria-wisdom-atoms/ from " + str(start))


_REPO = _find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(_REPO / "src"))

_SCRIPT = _find_staging_root(Path(__file__).resolve()) / "payload" / "scripts" / "wisdom_atoms.py"


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("wisdom_atoms", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_atoms():
    return _load_script()._make_atoms()


def test_wisdom_atom_count_is_12():
    """Exactly 12 operational wisdom atoms."""
    assert len(_get_atoms()) == 12


def test_all_atoms_are_pattern_kind():
    """Wisdom atoms are all PATTERN — predictive claims about regularities."""
    from sovereign_agent.stewardship.atoms import AtomKind
    atoms = _get_atoms()
    for atom in atoms:
        assert atom.kind == AtomKind.PATTERN, (
            f"Atom '{atom.title}' should be PATTERN, got {atom.kind}"
        )


def test_all_claims_substantial():
    """Every claim is at least 100 characters."""
    for atom in _get_atoms():
        assert len(atom.claim) >= 100, (
            f"Atom '{atom.title}' has short claim: {atom.claim[:60]!r}..."
        )


def test_all_atoms_have_wisdom_seed_tag():
    """Every atom carries 'wisdom-seed' tag."""
    for atom in _get_atoms():
        assert "wisdom-seed" in atom.tags, f"Atom '{atom.title}' missing 'wisdom-seed'"


def test_all_atoms_have_evidence_refs():
    """Every atom has at least one evidence_ref."""
    for atom in _get_atoms():
        assert len(atom.evidence_refs) >= 1, f"Atom '{atom.title}' has no evidence_refs"


def test_confidence_in_valid_range():
    """All confidence values in [0.0, 1.0]."""
    for atom in _get_atoms():
        assert 0.0 <= atom.confidence <= 1.0, (
            f"Atom '{atom.title}' has invalid confidence: {atom.confidence}"
        )


def test_no_low_confidence_atoms():
    """No wisdom atom has confidence below 0.85 (these are well-grounded patterns)."""
    atoms = _get_atoms()
    low_conf = [a for a in atoms if a.confidence < 0.85]
    assert len(low_conf) == 0, (
        f"Unexpected low-confidence atoms: {[(a.title, a.confidence) for a in low_conf]}"
    )


def test_titles_are_unique():
    """No duplicate titles."""
    atoms = _get_atoms()
    titles = [a.title for a in atoms]
    assert len(titles) == len(set(titles)), "Duplicate titles found"


def test_operating_pattern_tag_coverage():
    """At least 8 atoms are tagged 'operating-pattern'."""
    atoms = _get_atoms()
    tagged = [a for a in atoms if "operating-pattern" in a.tags]
    assert len(tagged) >= 8, f"Expected ≥8 operating-pattern atoms, got {len(tagged)}"


def test_staging_doctrine_covered():
    """At least 2 atoms reference the staging doctrine."""
    atoms = _get_atoms()
    staging = [a for a in atoms if "staging-doctrine" in a.tags]
    assert len(staging) >= 2, f"Expected ≥2 staging-doctrine atoms, got {len(staging)}"


def test_idempotency_skips_when_already_written(tmp_path):
    """If wisdom-seed atoms exist, main() skips writing."""
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStore

    store = AtomStore(tmp_path / "atoms.ndjson")
    store.append(Atom(
        kind=AtomKind.PATTERN,
        title="Pre-existing wisdom",
        claim="This is a pre-existing wisdom-seed atom for idempotency test purposes.",
        confidence=0.9,
        channels=["test"],
        tags=["wisdom-seed"],
        evidence_refs=["test"],
    ))

    mod = _load_script()
    captured = []
    with mock.patch.object(mod, "_atom_store", return_value=store):
        with mock.patch("builtins.print", side_effect=lambda *a: captured.append(str(a))):
            mod.main()

    assert any("already present" in s for s in captured)


def test_idempotency_writes_on_empty(tmp_path):
    """On an empty store, main() writes all 12 atoms."""
    from sovereign_agent.stewardship.atoms import AtomStore

    store = AtomStore(tmp_path / "atoms.ndjson")
    mod = _load_script()

    with mock.patch.object(mod, "_atom_store", return_value=store):
        mod.main()

    written = store.search(tag="wisdom-seed")
    assert len(written) == 12, f"Expected 12, got {len(written)}"


def test_partnership_atoms_reference_kevin():
    """At least one atom addresses Kevin's working style."""
    atoms = _get_atoms()
    kevin_atoms = [a for a in atoms if "kevin" in a.tags or "partnership" in a.channels]
    assert len(kevin_atoms) >= 1, "No atom addresses Kevin's working style"


def test_doctrine_channel_covered():
    """At least 6 atoms are in the doctrine channel."""
    atoms = _get_atoms()
    doctrine = [a for a in atoms if "doctrine" in a.channels]
    assert len(doctrine) >= 6, f"Expected ≥6 doctrine-channel atoms, got {len(doctrine)}"
