"""Behavior tests for aria-nested-core (Workstream E) — prove the patched
superpose.py actually works, using a shadow copy of the whole package
(never touches real src/). STAGED ONLY: never promoted — see
test_nested_core_live.py for the promoted, plain-import copy."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-nested-core" / "patcher.py").is_file():
            return candidate / "aria-nested-core"
    raise RuntimeError("could not locate aria-nested-core/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_superpose

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    sp = shadow / "sovereign_agent" / "nonclassical_supreme" / "superpose.py"
    patched, _ = patch_superpose(sp.read_text(encoding="utf-8"))
    sp.write_text(patched, encoding="utf-8")
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


def test_evolve_with_holo_weight_zero_is_byte_identical_to_baseline(shadow_pkg):
    """The single most important regression guard: holo_weight=0.0 (the
    default) must produce EXACTLY the same result as calling evolve()
    with no holo_weight at all — a true no-op, not an approximation."""
    from sovereign_agent.nonclassical_supreme.superpose import evolve, measure, prepare

    candidates = ["cats are great", "dogs are loyal", "the weather is nice"]

    state_a = prepare(candidates)
    evolve(state_a, "loyal dogs")
    result_a = measure(state_a, seed=0)

    state_b = prepare(candidates)
    evolve(state_b, "loyal dogs", holo_weight=0.0)
    result_b = measure(state_b, seed=0)

    assert result_a == result_b


def test_holographic_bias_returns_a_bias_per_candidate(shadow_pkg):
    from sovereign_agent.nonclassical_supreme.superpose import holographic_bias, prepare

    candidates = ["red apple", "blue sky", "green grass"]
    state = prepare(candidates)
    bias = holographic_bias(state, "the sky is blue")

    assert bias is not None
    assert len(bias) == len(candidates)
    assert all(0.0 <= b <= 1.0 for b in bias)


def test_evolve_with_positive_holo_weight_changes_the_result_distribution(shadow_pkg):
    """holo_weight > 0 must actually DO something — the amplitude
    distribution should differ from the baseline (proves the nesting is
    wired in, not silently ignored)."""
    from sovereign_agent.nonclassical_supreme.superpose import evolve, prepare

    candidates = ["red apple", "blue sky", "green grass", "yellow sun"]

    state_baseline = prepare(candidates)
    evolve(state_baseline, "sky", holo_weight=0.0)

    state_nested = prepare(candidates)
    evolve(state_nested, "sky", holo_weight=0.5)

    assert state_baseline.amplitudes != state_nested.amplitudes


def test_holographic_bias_never_raises_even_with_empty_candidates(shadow_pkg):
    from sovereign_agent.nonclassical_supreme.superpose import holographic_bias, prepare

    state = prepare([])
    bias = holographic_bias(state, "anything")
    assert bias == []


def test_evaluate_holographic_nesting_reports_honest_deltas(shadow_pkg):
    from sovereign_agent.nonclassical_supreme.superpose import evaluate_holographic_nesting

    cases = [
        {"query": "loyal dogs", "candidates": ["dogs are loyal", "cats are aloof"], "expected": "dogs are loyal"},
        {"query": "sunny weather", "candidates": ["it is sunny today", "it is raining"], "expected": "it is sunny today"},
    ]
    result = evaluate_holographic_nesting(cases, holo_weight=0.3)

    assert "baseline" in result
    assert "nested" in result
    assert "accuracy_delta" in result
    assert "confidence_delta" in result
    assert isinstance(result["nesting_helps"], bool)


def test_evaluate_holographic_nesting_never_claims_help_on_zero_delta(shadow_pkg):
    """If nested and baseline perform identically, nesting_helps must be
    False — no claim without proof."""
    from sovereign_agent.nonclassical_supreme.superpose import evaluate_holographic_nesting

    cases = [
        {"query": "x", "candidates": ["x"], "expected": "x"},
    ]
    result = evaluate_holographic_nesting(cases, holo_weight=0.3)
    assert result["accuracy_delta"] == 0.0
    # a single-candidate case can't show any real signal either way
    assert result["nesting_helps"] is False


def test_full_process_pipeline_still_works_unmodified(shadow_pkg):
    """Regression guard: the existing process() convenience function
    (prepare -> evolve -> measure) must still work exactly as before —
    it never passes holo_weight, so it must hit the untouched default."""
    from sovereign_agent.nonclassical_supreme.superpose import process

    result = process("blue sky", ["red apple", "blue sky", "green grass"])
    assert result["result"] == "blue sky"
