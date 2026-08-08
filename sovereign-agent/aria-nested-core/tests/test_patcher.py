"""Patcher tests for aria-nested-core — verify the patch function itself
against the CURRENT live superpose.py, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_superpose  # noqa: E402

REPO_ROOT = STAGING.parent
SUPERPOSE_PATH = (
    REPO_ROOT / "src" / "sovereign_agent" / "nonclassical_supreme" / "superpose.py"
)


def _live_text() -> str:
    return SUPERPOSE_PATH.read_text(encoding="utf-8")


def test_patch_applies_cleanly_against_live_superpose_py():
    new_text, _ = patch_superpose(_live_text())  # changed may be False if already applied
    assert MARK in new_text


def test_patch_is_idempotent():
    once, _ = patch_superpose(_live_text())
    twice, changed2 = patch_superpose(once)
    assert changed2 is False
    assert once == twice


def test_patched_file_compiles():
    import py_compile
    import tempfile

    new_text, _ = patch_superpose(_live_text())
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(new_text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


def test_evolve_gets_new_kwargs_with_zero_default():
    """holo_weight must default to 0.0 — an exact no-op — so every
    existing caller's behavior is byte-for-byte unchanged."""
    new_text, _ = patch_superpose(_live_text())
    sig_start = new_text.index("def evolve(")
    sig_slice = new_text[sig_start : sig_start + 400]
    assert "holo_weight: float = 0.0" in sig_slice
    assert "conditioner=None" in sig_slice


def test_evolve_only_blends_bias_when_holo_weight_positive():
    new_text, _ = patch_superpose(_live_text())
    body_start = new_text.index("def evolve(")
    body_slice = new_text[body_start : body_start + 2500]
    assert "if holo_weight > 0.0" in body_slice
    assert "holographic_bias(state, query" in body_slice


def test_holographic_bias_function_added_lazy_imports_torch():
    """torch/holo_bitnet must be imported INSIDE the function, never at
    module level — nonclassical_supreme's whole point is staying
    torch-free/CPU-only by default."""
    new_text, _ = patch_superpose(_live_text())
    assert "def holographic_bias(" in new_text
    func_start = new_text.index("def holographic_bias(")
    func_slice = new_text[func_start : func_start + 1600]
    assert "import torch" in func_slice
    assert "from sovereign_agent.aria_lm.holo_bitnet import HolographicConditioner" in func_slice
    # confirm NOT imported at module level (before the first def)
    first_def_idx = new_text.index("def _phase_of")
    module_header = new_text[:first_def_idx]
    assert "import torch" not in module_header


def test_holographic_bias_never_raises_returns_none_on_import_failure():
    new_text, _ = patch_superpose(_live_text())
    func_start = new_text.index("def holographic_bias(")
    func_slice = new_text[func_start : func_start + 1600]
    assert "except Exception" in func_slice
    assert "return None" in func_slice


def test_evaluate_holographic_nesting_added_with_honest_gate():
    new_text, _ = patch_superpose(_live_text())
    assert "def evaluate_holographic_nesting(" in new_text
    func_start = new_text.index("def evaluate_holographic_nesting(")
    func_slice = new_text[func_start : func_start + 2000]
    assert "nesting_helps" in func_slice
    assert "accuracy_delta" in func_slice
    assert "confidence_delta" in func_slice


def test_missing_anchor_raises_patch_error_not_silent_noop():
    with pytest.raises(PatchError):
        patch_superpose("this text has none of the expected anchors")


def test_already_patched_text_is_a_noop():
    once, _ = patch_superpose(_live_text())
    twice, changed = patch_superpose(once)
    assert changed is False
    assert twice == once
