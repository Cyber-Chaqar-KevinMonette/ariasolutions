"""Tests for M75 birth records — founding atoms and lineage tool.

Pre-apply: these tests inject the staging lineage_tool.py so they can run
before the apply script. They test both the founding_atoms.py script and
the lineage_tool.py tool.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ── Locate repo root (works from aria-birth-records/tests/ AND from tests/) ───

def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml found)")

_REPO = _repo_root()
_STAGING_TOOL = (
    _REPO / "aria-birth-records"
    / "payload" / "src" / "sovereign_agent" / "tools" / "lineage_tool.py"
)
_STAGING_SCRIPT = (
    _REPO / "aria-birth-records"
    / "payload" / "scripts" / "founding_atoms.py"
)


def _inject(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# lineage_tool is installed in src/ after apply — prefer live import
try:
    from sovereign_agent.tools.lineage_tool import LineageTool
    _lineage_mod = sys.modules.get("sovereign_agent.tools.lineage_tool")
except ImportError:
    _lineage_mod = _inject("sovereign_agent.tools.lineage_tool", _STAGING_TOOL)
    LineageTool = _lineage_mod.LineageTool

_script_mod = _inject("founding_atoms_script", _STAGING_SCRIPT)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_atom_store(tmp_path):
    from sovereign_agent.stewardship.atoms import AtomStore
    return AtomStore(tmp_path / "atoms.ndjson")


def _write_founding_atoms(store):
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStatus

    for atom in _script_mod._make_atoms():
        store.append(atom)


# ── Founding atoms script tests ───────────────────────────────────────────────


def test_founding_atoms_idempotent(tmp_path, monkeypatch):
    """Running the script twice produces exactly 6 atoms, no duplicates."""
    from sovereign_agent.stewardship.atoms import AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")

    def _mock_store():
        return store

    monkeypatch.setattr(_script_mod, "_atom_store", _mock_store)

    _script_mod.main()
    _script_mod.main()  # second call: should skip

    atoms = store.search(tag="birth-record")
    assert len(atoms) == 6, f"Expected 6, got {len(atoms)}"


def test_founding_atom_claim_not_empty():
    """All 6 founding atoms have non-empty claims of at least 50 characters."""
    atoms = _script_mod._make_atoms()
    for atom in atoms:
        assert len(atom.claim) >= 50, (
            f"Atom '{atom.title}' claim too short: {atom.claim!r}"
        )


def test_founding_atom_confidence():
    """FACT/RULE atoms have confidence=1.0."""
    atoms = _script_mod._make_atoms()
    for atom in atoms:
        assert atom.confidence == 1.0, (
            f"Atom '{atom.title}' has confidence={atom.confidence}, expected 1.0"
        )


def test_founding_atom_has_evidence_refs():
    """Every founding atom has at least 1 evidence_ref."""
    atoms = _script_mod._make_atoms()
    for atom in atoms:
        assert len(atom.evidence_refs) >= 1, (
            f"Atom '{atom.title}' has no evidence_refs"
        )


def test_founding_atoms_have_birth_record_tag():
    """Every founding atom carries the 'birth-record' tag."""
    atoms = _script_mod._make_atoms()
    for atom in atoms:
        assert "birth-record" in atom.tags, (
            f"Atom '{atom.title}' missing 'birth-record' tag"
        )


def test_milestone_atoms_count():
    """Exactly 3 atoms are tagged 'milestone'."""
    atoms = _script_mod._make_atoms()
    milestones = [a for a in atoms if "milestone" in a.tags]
    assert len(milestones) == 3


# ── LineageTool tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lineage_tool_no_atoms_graceful(tmp_path, monkeypatch):
    """When atom store is empty, returns ok=True with empty list and guidance note."""
    from sovereign_agent.stewardship.atoms import AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")

    monkeypatch.setattr(_lineage_mod, "_atom_store", lambda: store)

    tool = LineageTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["count"] == 0
    assert "Birth record not yet written" in result.output["note"]


@pytest.mark.asyncio
async def test_lineage_tool_birth_only_flag(tmp_path, monkeypatch):
    """birth_only=True returns only atoms tagged 'founding'."""
    from sovereign_agent.stewardship.atoms import AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    _write_founding_atoms(store)
    monkeypatch.setattr(_lineage_mod, "_atom_store", lambda: store)

    tool = LineageTool()
    result = await tool.execute(tool.Args(birth_only=True), trace_id="test")

    assert result.ok is True
    returned_tags = [set(a["tags"]) for a in result.output["atoms"]]
    for tags in returned_tags:
        assert "founding" in tags, f"Expected 'founding' in tags, got {tags}"


@pytest.mark.asyncio
async def test_lineage_tool_milestones_flag(tmp_path, monkeypatch):
    """milestones=True returns only atoms tagged 'milestone'."""
    from sovereign_agent.stewardship.atoms import AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    _write_founding_atoms(store)
    monkeypatch.setattr(_lineage_mod, "_atom_store", lambda: store)

    tool = LineageTool()
    result = await tool.execute(tool.Args(milestones=True), trace_id="test")

    assert result.ok is True
    assert result.output["count"] == 3
    for atom in result.output["atoms"]:
        assert "milestone" in atom["tags"]


@pytest.mark.asyncio
async def test_milestone_atoms_chronological(tmp_path, monkeypatch):
    """Atoms are returned oldest-first (by ts_created)."""
    from sovereign_agent.stewardship.atoms import AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    _write_founding_atoms(store)
    monkeypatch.setattr(_lineage_mod, "_atom_store", lambda: store)

    tool = LineageTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    timestamps = [a["ts_created"] for a in result.output["atoms"]]
    assert timestamps == sorted(timestamps), "Atoms are not in chronological order"


@pytest.mark.asyncio
async def test_lineage_tool_returns_all_birth_record_atoms(tmp_path, monkeypatch):
    """Default (both flags off) returns all 6 birth-record atoms."""
    from sovereign_agent.stewardship.atoms import AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    _write_founding_atoms(store)
    monkeypatch.setattr(_lineage_mod, "_atom_store", lambda: store)

    tool = LineageTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["count"] == 6
