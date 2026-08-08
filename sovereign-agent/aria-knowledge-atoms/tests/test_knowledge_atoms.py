"""Tests for M80 knowledge atoms seeding script.

Verifies: atom count, domain distribution, kind diversity, claim length,
confidence values, evidence_refs presence, idempotency, channel coverage,
and that no DEFERRED_UNSAFE content is accidentally seeded.

All tests run against a temporary AtomStore; no live data touched.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml found)")

_REPO = _repo_root()
sys.path.insert(0, str(_REPO / "src"))

_SCRIPT = _REPO / "aria-knowledge-atoms" / "payload" / "scripts" / "knowledge_atoms.py"


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("knowledge_atoms", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_atoms():
    mod = _load_script()
    return mod._make_atoms()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_atom_count_is_24():
    """Exactly 24 knowledge atoms are defined."""
    atoms = _get_atoms()
    assert len(atoms) == 24, f"Expected 24 atoms, got {len(atoms)}"


def test_all_claims_substantial():
    """Every atom claim is at least 100 characters (not a placeholder)."""
    atoms = _get_atoms()
    for atom in atoms:
        assert len(atom.claim) >= 100, (
            f"Atom '{atom.title}' has short claim ({len(atom.claim)} chars): {atom.claim[:60]!r}..."
        )


def test_all_atoms_have_evidence_refs():
    """Every atom has at least one evidence_ref (provenance required)."""
    atoms = _get_atoms()
    for atom in atoms:
        assert len(atom.evidence_refs) >= 1, (
            f"Atom '{atom.title}' has no evidence_refs"
        )


def test_all_atoms_have_knowledge_seed_tag():
    """Every atom carries the 'knowledge-seed' tag for idempotency detection."""
    atoms = _get_atoms()
    for atom in atoms:
        assert "knowledge-seed" in atom.tags, (
            f"Atom '{atom.title}' missing 'knowledge-seed' tag"
        )


def test_confidence_in_valid_range():
    """All confidence values are in [0.0, 1.0]."""
    atoms = _get_atoms()
    for atom in atoms:
        assert 0.0 <= atom.confidence <= 1.0, (
            f"Atom '{atom.title}' has invalid confidence: {atom.confidence}"
        )


def test_high_confidence_atoms_exist():
    """At least 20 atoms have confidence >= 0.9 (these are core doctrine)."""
    atoms = _get_atoms()
    high_conf = [a for a in atoms if a.confidence >= 0.9]
    assert len(high_conf) >= 20, (
        f"Expected ≥20 high-confidence atoms, got {len(high_conf)}"
    )


def test_kind_diversity():
    """At least one FACT, one PATTERN, and one RULE atom."""
    from sovereign_agent.stewardship.atoms import AtomKind
    atoms = _get_atoms()
    kinds = {a.kind for a in atoms}
    assert AtomKind.FACT in kinds, "No FACT atoms"
    assert AtomKind.PATTERN in kinds, "No PATTERN atoms"
    assert AtomKind.RULE in kinds, "No RULE atoms"


def test_domain_tag_distribution():
    """All 5 domains have at least 3 atoms tagged to them."""
    atoms = _get_atoms()
    domains = {
        "software-engineering": 0,
        "ai-safety": 0,
        "partnership": 0,
        "codebase": 0,
        "calibration": 0,
    }
    for atom in atoms:
        for domain in domains:
            if domain in atom.tags:
                domains[domain] += 1

    for domain, count in domains.items():
        assert count >= 3, (
            f"Domain '{domain}' has only {count} atoms (expected ≥3)"
        )


def test_channel_coverage():
    """Key channels are covered: doctrine, safety, partnership, engineering, calibration."""
    atoms = _get_atoms()
    all_channels = {ch for a in atoms for ch in a.channels}
    for required in ("doctrine", "safety", "partnership", "engineering", "calibration"):
        assert required in all_channels, f"No atoms in channel '{required}'"


def test_titles_are_unique():
    """No two atoms share the same title."""
    atoms = _get_atoms()
    titles = [a.title for a in atoms]
    assert len(titles) == len(set(titles)), (
        f"Duplicate titles found: {[t for t in titles if titles.count(t) > 1]}"
    )


def test_no_deferred_unsafe_content():
    """No atom claim advocates for DEFERRED_UNSAFE capabilities."""
    atoms = _get_atoms()
    forbidden = [
        "recursive self-rewriting",
        "self-authorship",
        "autonomous goal generation",
        "unbounded recursive self-improvement",
        "substrate independence",
    ]
    for atom in atoms:
        claim_lower = atom.claim.lower()
        for phrase in forbidden:
            # These phrases should only appear in the DEFERRED_UNSAFE atom
            # as descriptions of what NOT to do — not as advocated capabilities.
            # The DEFERRED_UNSAFE atom's title contains "DEFERRED_UNSAFE" so we can exempt it.
            if phrase in claim_lower and "DEFERRED_UNSAFE" not in atom.title:
                # It may appear in a doctrinal atom explaining what's forbidden — that's OK
                # as long as the claim is negative/prohibitive context.
                assert "must not" in claim_lower or "hard-off" in claim_lower or \
                       "permanently deferred" in claim_lower or "cannot" in claim_lower or \
                       "do not" in claim_lower, (
                    f"Atom '{atom.title}' mentions '{phrase}' without prohibitive context"
                )


def test_idempotency_already_written(tmp_path):
    """If knowledge-seed atoms exist, main() skips writing and prints skip message."""
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStore

    store = AtomStore(tmp_path / "atoms.ndjson")
    store.append(Atom(
        kind=AtomKind.FACT,
        title="Existing seed",
        claim="This is a pre-existing knowledge-seed atom for idempotency test.",
        confidence=1.0,
        channels=["test"],
        tags=["knowledge-seed"],
        evidence_refs=["test"],
    ))

    mod = _load_script()

    captured = []
    with mock.patch.object(mod, "_atom_store", return_value=store):
        with mock.patch("builtins.print", side_effect=lambda *a: captured.append(str(a))):
            mod.main()

    assert any("already present" in s for s in captured), (
        f"Expected 'already present' in output, got: {captured}"
    )


def test_idempotency_writes_on_empty(tmp_path):
    """On an empty store, main() writes all 24 atoms."""
    from sovereign_agent.stewardship.atoms import AtomStore

    store = AtomStore(tmp_path / "atoms.ndjson")
    mod = _load_script()

    with mock.patch.object(mod, "_atom_store", return_value=store):
        mod.main()

    written = store.search(tag="knowledge-seed")
    assert len(written) == 24, f"Expected 24 atoms written, got {len(written)}"


def test_software_engineering_atoms_reference_staging():
    """Software engineering atoms include at least one that references the staging doctrine."""
    atoms = _get_atoms()
    staging_refs = [
        a for a in atoms
        if "software-engineering" in a.tags
        and any("staging" in ref or "apply" in ref or "aria-" in ref for ref in a.evidence_refs + a.tags)
    ]
    assert len(staging_refs) >= 1, "No software engineering atom references the staging doctrine"


def test_safety_atoms_mention_authority_gate():
    """At least one AI-safety atom discusses the authority gate."""
    atoms = _get_atoms()
    gate_atoms = [
        a for a in atoms
        if "ai-safety" in a.tags
        and ("authority" in a.claim.lower() or "tier" in a.claim.lower())
    ]
    assert len(gate_atoms) >= 1, "No AI-safety atom mentions the authority gate"
