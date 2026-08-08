"""Tests for M85 aria_metrics — confidence-grounding observability tool."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root")


_REPO = _repo_root()
_MOD_PATH = (
    _REPO / "aria-observability" / "payload" / "src"
    / "sovereign_agent" / "tools" / "aria_metrics.py"
)


def _inject(mod_name, file_path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_metrics_module():
    """Prefer the installed package (post-apply); fall back to staging payload.

    Once tools/__init__.py imports aria_metrics, injecting the staging file
    under the same module name causes a circular import — so use live first.
    """
    try:
        import sovereign_agent.tools.aria_metrics as live
        return live
    except Exception:
        return _inject("sovereign_agent.tools.aria_metrics", _MOD_PATH)


_mod = _load_metrics_module()


def _patch_data_dir(tmp_path: Path, monkeypatch):
    class _Paths:
        data_dir = tmp_path / "data"
    class _Settings:
        paths = _Paths()
    _Paths.data_dir.mkdir(parents=True, exist_ok=True)
    import sovereign_agent.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "SETTINGS", _Settings(), raising=False)
    return _Paths.data_dir


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_empty_data_returns_ok(tmp_path, monkeypatch):
    """Empty data dir → ok=True with zero/null values (graceful degradation)."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _mod.AriaMetricsTool()
    result = await tool.execute(tool.Args(), trace_id="t")
    assert result.ok
    assert "confidence_statement" in result.output
    assert "atoms" in result.output
    assert result.output["atoms"]["atom_count"] == 0


@pytest.mark.anyio
async def test_confidence_statement_is_string(tmp_path, monkeypatch):
    """confidence_statement is always a non-empty string."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _mod.AriaMetricsTool()
    result = await tool.execute(tool.Args(), trace_id="t")
    stmt = result.output["confidence_statement"]
    assert isinstance(stmt, str)
    assert len(stmt) > 0


@pytest.mark.anyio
async def test_atom_metrics_with_real_atoms(tmp_path, monkeypatch):
    """Atom metrics count active atoms correctly."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)

    # Write 3 atoms directly to atoms.ndjson
    atoms_path = data_dir / "atoms.ndjson"
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStatus
    from dataclasses import asdict
    for i in range(3):
        atom = Atom(
            title=f"Test atom {i}",
            claim=f"Claim {i}",
            kind=AtomKind.FACT,
            confidence=0.7 + i * 0.1,
            status=AtomStatus.ACTIVE,
        )
        with atoms_path.open("a") as f:
            f.write(json.dumps(asdict(atom), default=str) + "\n")

    metrics = _mod._atom_metrics(data_dir)
    assert metrics["atom_count"] == 3
    assert metrics["avg_confidence"] > 0
    assert "fact" in metrics["kind_distribution"]


@pytest.mark.anyio
async def test_calibration_metrics_with_resolved(tmp_path, monkeypatch):
    """Calibration accuracy computed from resolved predictions."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)
    cal_path = data_dir / "calibration" / "ledger.ndjson"
    cal_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    entries = [
        {"entry_id": "a", "claim": "x", "confidence": 0.8, "domain": "test",
         "ts": now, "outcome_correct": True},
        {"entry_id": "b", "claim": "y", "confidence": 0.7, "domain": "test",
         "ts": now, "outcome_correct": True},
        {"entry_id": "c", "claim": "z", "confidence": 0.9, "domain": "test",
         "ts": now, "outcome_correct": False},
    ]
    with cal_path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    cal = _mod._calibration_metrics(data_dir)
    assert cal["resolved_count"] == 3
    # 2 correct out of 3 = ~0.667
    assert abs(cal["calibration_accuracy"] - 0.667) < 0.01


@pytest.mark.anyio
async def test_flaw_metrics_counts_by_severity(tmp_path, monkeypatch):
    """Flaw metrics count open flaws by severity correctly."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)
    flaw_path = data_dir / "flaws" / "catalog.ndjson"
    flaw_path.parent.mkdir(parents=True, exist_ok=True)

    flaws = [
        {"flaw_id": "F1", "severity": "critical", "status": "open"},
        {"flaw_id": "F2", "severity": "notable", "status": "open"},
        {"flaw_id": "F3", "severity": "watch", "status": "resolved"},
    ]
    with flaw_path.open("w") as f:
        for fl in flaws:
            f.write(json.dumps(fl) + "\n")

    fm = _mod._flaw_metrics(data_dir)
    assert fm["open_critical"] == 1
    assert fm["open_notable"] == 1
    assert fm["resolved"] == 1
    assert fm["total"] == 3


@pytest.mark.anyio
async def test_honor_metrics_counts_care_signals(tmp_path, monkeypatch):
    """Honor metrics count care signals from kevin->aria."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)
    from sovereign_agent.stewardship.honor import HonorLedger, kevin_honors_aria

    ledger_path = data_dir / "honor" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = HonorLedger(ledger_path)

    for _ in range(3):
        ledger.append(kevin_honors_aria("heart", tags=["heart", "reaction"]))

    honor = _mod._honor_metrics(data_dir)
    assert honor["care_signals_total"] == 3
    assert honor["honor_data_ok"]


@pytest.mark.anyio
async def test_confidence_statement_includes_atoms_and_flaws(tmp_path, monkeypatch):
    """Confidence statement mentions atoms and flaws when data exists."""
    data_dir = _patch_data_dir(tmp_path, monkeypatch)

    # Write one atom
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStatus
    from dataclasses import asdict
    atom = Atom(title="T", claim="C", kind=AtomKind.FACT,
                confidence=0.8, status=AtomStatus.ACTIVE)
    atoms_path = data_dir / "atoms.ndjson"
    with atoms_path.open("w") as f:
        f.write(json.dumps(asdict(atom), default=str) + "\n")

    # Write one critical flaw
    flaw_path = data_dir / "flaws" / "catalog.ndjson"
    flaw_path.parent.mkdir(parents=True, exist_ok=True)
    with flaw_path.open("w") as f:
        f.write(json.dumps({"flaw_id": "F1", "severity": "critical", "status": "open"}) + "\n")

    tool = _mod.AriaMetricsTool()
    result = await tool.execute(tool.Args(), trace_id="t")
    stmt = result.output["confidence_statement"]

    assert "atom" in stmt
    assert "1 critical" in stmt


@pytest.mark.anyio
async def test_full_output_structure(tmp_path, monkeypatch):
    """Full output has all expected top-level keys."""
    _patch_data_dir(tmp_path, monkeypatch)
    tool = _mod.AriaMetricsTool()
    result = await tool.execute(tool.Args(), trace_id="t")
    assert result.ok
    for key in ("confidence_statement", "atoms", "calibration", "honor", "flaws", "ts"):
        assert key in result.output
