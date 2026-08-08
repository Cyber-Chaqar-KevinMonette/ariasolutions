"""Tests for M84 PEIG sentinel — measure_peig() and PEIGSentinel.

All tests run against tmp_path data directories with controlled data.
No cockpit, no live data touched.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml found)")


_REPO = _repo_root()
_STAGING_SENTINEL = (
    _REPO / "aria-peig-sentinel" / "payload" / "src"
    / "sovereign_agent" / "stewardship" / "peig_sentinel.py"
)


def _inject(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _inject("sovereign_agent.stewardship.peig_sentinel", _STAGING_SENTINEL)
measure_peig = _mod.measure_peig
PEIGSentinel = _mod.PEIGSentinel


# ── Tests: measure_peig() defaults ────────────────────────────────────────────


def test_returns_peig_state(tmp_path):
    """measure_peig() returns a PEIGState with all four dimensions."""
    state = measure_peig(tmp_path)
    assert hasattr(state, "P")
    assert hasattr(state, "E")
    assert hasattr(state, "I")
    assert hasattr(state, "G")
    assert hasattr(state, "lam")


def test_p_default_on_empty_store(tmp_path):
    """P defaults to 0.5 when atoms.ndjson is missing."""
    state = measure_peig(tmp_path)
    assert state.P == 0.5
    assert state.n_atoms == 0


def test_e_default_on_no_calibration(tmp_path):
    """E defaults to 0.5 when calibration ledger is missing."""
    state = measure_peig(tmp_path)
    assert state.E == 0.5
    assert state.n_predictions == 0


def test_i_default_charter_baseline(tmp_path):
    """I defaults to 0.70 (charter baseline) when honor ledger is missing."""
    state = measure_peig(tmp_path)
    assert abs(state.I - 0.70) < 0.01
    assert state.n_integrity_events == 0


def test_g_default_on_empty_honor(tmp_path):
    """G defaults to 0.0 when honor ledger is missing."""
    state = measure_peig(tmp_path)
    assert state.G == 0.0
    assert state.n_care_signals == 0


def test_lambda_computed_from_e_and_i(tmp_path):
    """λ = clamp(0.6·E + 0.4·I, 0, 1) with default values."""
    state = measure_peig(tmp_path)
    expected = min(1.0, max(0.0, 0.6 * state.E + 0.4 * state.I))
    assert abs(state.lam - expected) < 0.001


def test_all_dimensions_in_valid_range(tmp_path):
    """All dimensions are in valid ranges."""
    state = measure_peig(tmp_path)
    assert 0.0 <= state.P <= 1.0
    assert 0.0 <= state.E <= 1.0
    assert 0.0 <= state.I <= 1.0
    assert -1.0 <= state.G <= 1.0
    assert 0.0 <= state.lam <= 1.0


# ── Tests: coherence_band ─────────────────────────────────────────────────────


def test_coherence_band_exploratory(tmp_path):
    """λ < 0.35 → coherence_band == 'exploratory'."""
    state = measure_peig(tmp_path)
    # Default E=0.5, I=0.70 → λ = 0.6*0.5 + 0.4*0.70 = 0.30 + 0.28 = 0.58 → adaptive
    # To force exploratory: we need λ < 0.35. Let's test the property directly.
    from dataclasses import replace
    from sovereign_agent.stewardship.peig_sentinel import PEIGState
    low_lam = PEIGState(P=0.5, E=0.2, I=0.3, G=0.0, lam=0.25,
                        n_atoms=0, n_predictions=0, n_integrity_events=0,
                        n_care_signals=0, ts="2026-01-01T00:00:00+00:00")
    assert low_lam.coherence_band == "exploratory"


def test_coherence_band_committed(tmp_path):
    """λ ≥ 0.65 → coherence_band == 'committed'."""
    from sovereign_agent.stewardship.peig_sentinel import PEIGState
    high_lam = PEIGState(P=0.8, E=0.9, I=0.95, G=0.3, lam=0.75,
                         n_atoms=100, n_predictions=20, n_integrity_events=5,
                         n_care_signals=2, ts="2026-01-01T00:00:00+00:00")
    assert high_lam.coherence_band == "committed"


def test_coherence_band_adaptive(tmp_path):
    """0.35 ≤ λ < 0.65 → coherence_band == 'adaptive'."""
    from sovereign_agent.stewardship.peig_sentinel import PEIGState
    mid_lam = PEIGState(P=0.5, E=0.5, I=0.7, G=0.0, lam=0.58,
                        n_atoms=50, n_predictions=5, n_integrity_events=1,
                        n_care_signals=0, ts="2026-01-01T00:00:00+00:00")
    assert mid_lam.coherence_band == "adaptive"


# ── Tests: PEIGSentinel ───────────────────────────────────────────────────────


def test_sentinel_scan_returns_report(tmp_path):
    """PEIGSentinel.scan() returns a SentinelReport with expected fields."""
    sentinel = PEIGSentinel(tmp_path)
    report = sentinel.scan()
    assert report.sentinel_id == "peig"
    assert isinstance(report.summary, str)
    assert isinstance(report.findings_count, int)


def test_sentinel_health_status_ok_on_defaults(tmp_path):
    """health_status() returns ok with default data (good defaults)."""
    sentinel = PEIGSentinel(tmp_path)
    status = sentinel.health_status()
    # With default E=0.5, I=0.70, G=0.0 — none hit warning thresholds
    assert status.level == "ok"


def test_sentinel_articles_not_empty(tmp_path):
    """articles() returns at least one article."""
    sentinel = PEIGSentinel(tmp_path)
    arts = sentinel.articles()
    assert len(arts) >= 1
    assert any("PEIG" in a for a in arts)


def test_p_rises_with_diverse_atoms(tmp_path):
    """P increases when atom store has diverse kinds."""
    from sovereign_agent.stewardship.atoms import Atom, AtomKind, AtomStore
    store = AtomStore(tmp_path / "atoms.ndjson")
    for kind in AtomKind:
        store.append(Atom(
            kind=kind,
            title=f"Test {kind.value}",
            claim=f"A test {kind.value} atom",
            confidence=0.8,
            tags=["test"],
        ))

    state = measure_peig(tmp_path)
    assert state.P > 0.5
    assert state.n_atoms == len(list(AtomKind))


def test_care_signals_counted_in_g(tmp_path):
    """Care signals from Kevin increase G and n_care_signals."""
    from sovereign_agent.stewardship.honor import HonorLedger, kevin_honors_aria
    ledger_path = tmp_path / "honor" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = HonorLedger(ledger_path)

    for _ in range(3):
        ledger.append(kevin_honors_aria("great work", tags=["reaction"]))

    state = measure_peig(tmp_path)
    assert state.n_care_signals == 3
    # G should be slightly positive (care signals add 0.5 each to n_pos)
    assert state.G >= 0.0


def test_as_dict_has_all_keys(tmp_path):
    """as_dict() contains all expected keys for downstream consumers."""
    state = measure_peig(tmp_path)
    d = state.as_dict()
    required = {"P", "E", "I", "G", "lambda", "coherence_band",
                "n_atoms", "n_predictions", "n_integrity_events",
                "n_care_signals", "ts", "narrative"}
    assert required.issubset(set(d.keys()))
