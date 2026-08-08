"""training_config.py — named, selectable fine-tuning configurations.

Kevin, 2026-07-21: "bake fp16 data into her system verbosely and create a
configuration for me to select for this task. Prepare Aria and me for
this work."

Before this module, model_trainer.py's hyperparameters (base model,
precision, LoRA rank, epochs) were just function defaults — real, but
buried, and only reachable by calling Python directly. This is the
standing, selectable version: named presets, each one carrying its FULL
reasoning as a real field on the object (not a comment you have to go
find in a different file), so picking a preset is picking a documented,
verbose set of choices, not a mystery.

Same "prove, don't assume" spirit as model_ladder.py: nothing here
promises a preset will train quickly or well on your exact hardware --
`sov train run <preset>` runs it for real and reports the honest result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# hardware-precision-d (Kevin, 2026-07-21): "bake fp16 data into her
# system verbosely." This machine's GPU is a GTX 1070 -- Pascal,
# compute capability 6.1 (confirmed directly via
# torch.cuda.get_device_capability(0), not assumed from the model name).
# Pascal has no real bf16 TENSOR CORE path -- bf16 ops either silently
# fall back to slow emulation or misbehave depending on the exact op.
# fp16 is the correct, well-supported choice on this exact card. Stated
# here, verbosely, as a real named constant with its own reasoning --
# not a bare `torch.float16` buried inside a training function.
HARDWARE_PRECISION = "fp16"
HARDWARE_PRECISION_REASON = (
    "GTX 1070 (Pascal, compute capability 6.1) has no real bf16 "
    "tensor-core support -- fp16 is the correct precision on this card, "
    "confirmed via torch.cuda.get_device_capability(0), not assumed."
)


@dataclass(frozen=True)
class TrainingConfig:
    key: str
    title: str
    description: str
    base_model: str
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    epochs: int
    learning_rate: float
    min_examples: int
    precision: str = HARDWARE_PRECISION
    precision_reason: str = HARDWARE_PRECISION_REASON

    def summary_lines(self) -> list[str]:
        """Every real choice this preset makes, spelled out — the
        "verbose" part of "bake fp16 data into her system verbosely":
        picking a preset should show you everything it actually does."""
        return [
            f"base model: {self.base_model}",
            f"precision: {self.precision} — {self.precision_reason}",
            f"LoRA: r={self.lora_r}, alpha={self.lora_alpha}, dropout={self.lora_dropout}",
            f"epochs: {self.epochs} · learning rate: {self.learning_rate}",
            f"minimum examples required: {self.min_examples}",
        ]


# base-model-fits-vram-d (Kevin, 2026-07-21): the first REAL run of
# quick-test on phi4-mini (3.8B) OOM'd -- confirmed directly, not
# theorized: loading the frozen fp16 weights alone took 6.87 GiB out of
# 7.92 GiB total, leaving ~75 MiB free before training even reached its
# first optimizer step. A 3.8B model in fp16 has no real headroom left
# for activations/gradients/LoRA state on an 8GB card. Switched both
# presets to Qwen2.5-1.5B-Instruct -- ~3GB of weights in fp16, leaving
# genuine room to actually train. This also matches what was actually
# asked for at the very start of this project ("a FAST AI model"), not
# a regression.
TRAINING_PRESETS: dict[str, TrainingConfig] = {
    "quick-test": TrainingConfig(
        key="quick-test",
        title="Quick test",
        description=(
            "Fast validation run — 1 epoch, small LoRA rank. Confirms the "
            "whole pipeline (data → LoRA → adapter) actually works end to "
            "end before committing to a longer run. Not meant to produce "
            "a dramatically different model on its own."
        ),
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        lora_r=8, lora_alpha=16, lora_dropout=0.05,
        epochs=1, learning_rate=2e-4, min_examples=20,
    ),
    "standard": TrainingConfig(
        key="standard",
        title="Standard",
        description=(
            "A real fine-tuning pass — 3 epochs, a fuller LoRA rank. The "
            "one to run once quick-test has confirmed the pipeline works."
        ),
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        lora_r=16, lora_alpha=32, lora_dropout=0.05,
        epochs=3, learning_rate=2e-4, min_examples=20,
    ),
}


def get_preset(key: str) -> TrainingConfig:
    if key not in TRAINING_PRESETS:
        raise KeyError(
            f"unknown training preset {key!r} — choices: "
            f"{', '.join(TRAINING_PRESETS)}"
        )
    return TRAINING_PRESETS[key]


__all__ = [
    "HARDWARE_PRECISION", "HARDWARE_PRECISION_REASON",
    "TrainingConfig", "TRAINING_PRESETS", "get_preset",
]
