"""Behavior tests for aria-nested-core, promoted to live tests/ — tests
the REAL, already-patched `sovereign_agent.nonclassical_supreme.superpose`
directly, no shadow copy, no `sys.modules` manipulation. See
test_nested_core.py (staged only) for the shadow-copy pre-apply version.
"""
from __future__ import annotations


def test_evolve_with_holo_weight_zero_is_byte_identical_to_baseline():
    from sovereign_agent.nonclassical_supreme.superpose import evolve, measure, prepare

    candidates = ["cats are great", "dogs are loyal", "the weather is nice"]

    state_a = prepare(candidates)
    evolve(state_a, "loyal dogs")
    result_a = measure(state_a, seed=0)

    state_b = prepare(candidates)
    evolve(state_b, "loyal dogs", holo_weight=0.0)
    result_b = measure(state_b, seed=0)

    assert result_a == result_b


def test_holographic_bias_returns_a_bias_per_candidate():
    from sovereign_agent.nonclassical_supreme.superpose import holographic_bias, prepare

    candidates = ["red apple", "blue sky", "green grass"]
    state = prepare(candidates)
    bias = holographic_bias(state, "the sky is blue")

    assert bias is not None
    assert len(bias) == len(candidates)
    assert all(0.0 <= b <= 1.0 for b in bias)


def test_evolve_with_positive_holo_weight_changes_the_result_distribution():
    from sovereign_agent.nonclassical_supreme.superpose import evolve, prepare

    candidates = ["red apple", "blue sky", "green grass", "yellow sun"]

    state_baseline = prepare(candidates)
    evolve(state_baseline, "sky", holo_weight=0.0)

    state_nested = prepare(candidates)
    evolve(state_nested, "sky", holo_weight=0.5)

    assert state_baseline.amplitudes != state_nested.amplitudes


def test_holographic_bias_never_raises_even_with_empty_candidates():
    from sovereign_agent.nonclassical_supreme.superpose import holographic_bias, prepare

    state = prepare([])
    bias = holographic_bias(state, "anything")
    assert bias == []


def test_evaluate_holographic_nesting_reports_honest_deltas():
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


def test_evaluate_holographic_nesting_never_claims_help_on_zero_delta():
    from sovereign_agent.nonclassical_supreme.superpose import evaluate_holographic_nesting

    cases = [
        {"query": "x", "candidates": ["x"], "expected": "x"},
    ]
    result = evaluate_holographic_nesting(cases, holo_weight=0.3)
    assert result["accuracy_delta"] == 0.0
    assert result["nesting_helps"] is False


def test_full_process_pipeline_still_works_unmodified():
    from sovereign_agent.nonclassical_supreme.superpose import process

    result = process("blue sky", ["red apple", "blue sky", "green grass"])
    assert result["result"] == "blue sky"
