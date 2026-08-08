"""Tests for training_config — named, selectable fine-tuning presets.

Kevin, 2026-07-21: "bake fp16 data into her system verbosely and create a
configuration for me to select for this task."
"""
from __future__ import annotations

import pytest


def test_every_preset_uses_fp16_verbosely():
    """The whole point: fp16 must be a real, documented field on every
    preset, not a bare hardcoded value buried in the trainer."""
    from sovereign_agent.training_config import TRAINING_PRESETS

    for preset in TRAINING_PRESETS.values():
        assert preset.precision == "fp16"
        assert "Pascal" in preset.precision_reason
        assert "6.1" in preset.precision_reason


def test_summary_lines_include_every_real_choice():
    from sovereign_agent.training_config import get_preset

    preset = get_preset("quick-test")
    lines = "\n".join(preset.summary_lines())
    assert preset.base_model in lines
    assert "fp16" in lines
    assert str(preset.lora_r) in lines
    assert str(preset.epochs) in lines
    assert str(preset.min_examples) in lines


def test_get_preset_raises_with_choices_listed():
    from sovereign_agent.training_config import get_preset

    with pytest.raises(KeyError, match="quick-test"):
        get_preset("not-a-real-preset")


def test_quick_test_is_smaller_than_standard():
    """quick-test must genuinely be the faster/smaller of the two --
    it exists specifically to validate the pipeline before a longer run."""
    from sovereign_agent.training_config import get_preset

    quick = get_preset("quick-test")
    standard = get_preset("standard")
    assert quick.epochs < standard.epochs
    assert quick.lora_r <= standard.lora_r


def test_both_presets_share_a_base_model_small_enough_to_actually_train():
    """base-model-fits-vram-d: the first real run on phi4-mini (3.8B)
    OOM'd -- loading its frozen fp16 weights alone took 6.87 of the 7.92
    GiB card, leaving no room to train. Switched to Qwen2.5-1.5B-Instruct
    (~3GB in fp16) -- confirmed real headroom, not just a smaller number."""
    from sovereign_agent.training_config import TRAINING_PRESETS

    for preset in TRAINING_PRESETS.values():
        assert "qwen2.5-1.5b" in preset.base_model.lower()
