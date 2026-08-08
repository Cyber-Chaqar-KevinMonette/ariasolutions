"""Tests for Genesis-Seeds distillation: seed atoms + genesis_distill tool."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("repo root not found")


_REPO = _repo_root()
sys.path.insert(0, str(_REPO / "src"))
_ATOMS_SCRIPT = _REPO / "aria-genesis-distill" / "payload" / "scripts" / "genesis_atoms.py"
_TOOL_PATH = (
    _REPO / "aria-genesis-distill" / "payload" / "src"
    / "sovereign_agent" / "tools" / "genesis_distill_tool.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _atoms():
    return _load("genesis_atoms", _ATOMS_SCRIPT)._make_atoms()


def _load_tool():
    """Prefer installed package (post-apply); fall back to staging payload."""
    try:
        import sovereign_agent.tools.genesis_distill_tool as live
        return live
    except Exception:
        return _load("sovereign_agent.tools.genesis_distill_tool", _TOOL_PATH)


# ── Atom tests ────────────────────────────────────────────────────────────────

def test_seven_atoms_defined():
    assert len(_atoms()) == 7


def test_all_tagged_genesis_seed():
    assert all("genesis-seed" in a.tags for a in _atoms())


def test_honest_framing_atom_present_and_first():
    atoms = _atoms()
    first = atoms[0]
    assert "honest-framing" in first.tags
    claim = first.claim.lower()
    assert "not" in claim and ("physics" in claim and "consciousness" in claim)
    assert "substrate independence" in claim


def test_confidence_in_range():
    for a in _atoms():
        assert 0.85 <= a.confidence <= 0.99


def test_all_have_evidence_refs():
    for a in _atoms():
        assert a.evidence_refs, f"{a.title} has no evidence_refs"
        assert any("Genesis-Seeds" in r for r in a.evidence_refs)


def test_no_deferred_unsafe_advocacy():
    banned = ["recursive self-code-rewrit", "self-author", "autonomous goal generation",
              "unbounded recursive self-improvement", "edit its own code", "edit her own code"]
    for a in _atoms():
        text = (a.title + " " + a.claim).lower()
        for b in banned:
            assert b not in text, f"{a.title} advocates DEFERRED_UNSAFE: {b}"


def test_lambda_and_bridge_blocks_present():
    titles = " ".join(a.title.lower() for a in _atoms())
    assert "λ-mixing" in titles or "lambda" in titles or "mixing" in titles
    assert "bridge" in titles
    assert "node" in titles


def test_advisory_only_governance():
    # The witnessing atom must enshrine advisory-only.
    joined = " ".join(a.claim.lower() for a in _atoms())
    assert "advisory" in joined and "kevin always decides" in joined


# ── Tool tests ────────────────────────────────────────────────────────────────

def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "Genesis-Seeds"
    (root / "sub").mkdir(parents=True)
    (root / "readme.md").write_text("# Title line long enough\nbody")
    (root / "sub" / "code.py").write_text("# purpose of this module here\nx=1")
    (root / "paper.pdf").write_bytes(b"%PDF-1.4 binary")
    return root


def _run(tool, args):
    return asyncio.run(tool.execute(args, trace_id="t"))


def test_tool_inventory_lists_text_and_binary(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.setenv("GENESIS_SEEDS_DIR", str(root))
    mod = _load_tool()
    tool = mod.GenesisDistillTool()
    res = _run(tool, tool.Args(area="", mode="inventory"))
    assert res.ok
    assert res.output["text_count"] == 2
    assert res.output["binary_count"] == 1


def test_tool_read_returns_content(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.setenv("GENESIS_SEEDS_DIR", str(root))
    mod = _load_tool()
    tool = mod.GenesisDistillTool()
    res = _run(tool, tool.Args(area="readme.md", mode="read"))
    assert res.ok
    assert "Title line" in res.output["content"]


def test_tool_rejects_binary_read(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.setenv("GENESIS_SEEDS_DIR", str(root))
    mod = _load_tool()
    tool = mod.GenesisDistillTool()
    res = _run(tool, tool.Args(area="paper.pdf", mode="read"))
    assert not res.ok
    assert "read_error" in res.error


def test_tool_blocks_path_escape(tmp_path, monkeypatch):
    root = _make_corpus(tmp_path)
    monkeypatch.setenv("GENESIS_SEEDS_DIR", str(root))
    mod = _load_tool()
    tool = mod.GenesisDistillTool()
    res = _run(tool, tool.Args(area="../../etc/passwd", mode="read"))
    assert not res.ok
    assert "not_found" in res.error


def test_tool_tier_is_one(tmp_path, monkeypatch):
    mod = _load_tool()
    assert mod.GenesisDistillTool().tier == 1
