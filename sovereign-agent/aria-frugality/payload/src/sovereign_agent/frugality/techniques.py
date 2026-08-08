"""frugality/techniques.py — the god-tier hardware-reduction technique catalog.

The constructive answer to "how far can we go on a GTX 1070 (8GB)." Every method to shrink VRAM /
compute, honestly scored: VRAM saving, compute saving, quality cost, implementation effort, and status
(built · available · planned). No hype — honest tradeoffs, because a frugality claim that overstates
savings is exactly what the Tribunal exists to catch.

The savings figures are honest order-of-magnitude estimates for a small decoder transformer; the planner
(`planner.py`) does the real per-model arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Technique:
    id: str
    name: str
    vram_save: str            # qualitative: none | low | medium | high | extreme
    compute_save: str
    quality_cost: str         # none | low | medium | high
    effort: str               # low | medium | high
    status: str               # built | available | planned
    where: str                # training | inference | both
    note: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("id", "name", "vram_save", "compute_save", "quality_cost", "effort", "status", "where", "note")}


CATALOG: list[Technique] = [
    Technique("ternary-bitnet", "Ternary BitNet (b1.58)", "extreme", "high", "low-medium", "medium", "built",
              "inference",
              "Weights → {−1,0,+1} (~1.58 bits) + 8-bit activations + STE. ~10× smaller weights vs fp16, "
              "matmuls become add/subtract. Built & proven to still learn (aria_lm/bitnet.py). The big lever."),
    Technique("int8-quant", "8-bit inference quant", "high", "medium", "low", "low", "available", "inference",
              "Post-training int8 weights → 2× smaller than fp16, tiny quality cost. Standard."),
    Technique("int4-quant", "4-bit inference quant (NF4/GPTQ-style)", "high", "medium", "medium", "medium",
              "available", "inference", "~4× smaller than fp16; some quality cost. Pairs with QLoRA."),
    Technique("qlora", "QLoRA fine-tuning", "high", "low", "low", "medium", "planned", "training",
              "Train tiny LoRA adapters over a frozen 4-bit base → fine-tune big models in little VRAM. "
              "Reversible/detachable (Ring-2)."),
    Technique("grad-checkpoint", "Gradient checkpointing", "high", "negative", "none", "low", "available",
              "training", "Recompute activations in backward instead of storing them → trade ~30% compute "
              "for big activation-memory savings. Lets a bigger model fit."),
    Technique("grad-accum", "Gradient accumulation", "medium", "none", "none", "low", "built", "training",
              "Simulate a large batch with many micro-batches → fit training in small VRAM. Already in train.py."),
    Technique("mixed-precision", "Mixed precision (fp16/bf16)", "medium", "high", "none", "low", "built",
              "both", "Half-precision compute/storage; ~2× vs fp32. Already in train.py (AMP)."),
    Technique("cpu-offload", "CPU / NVMe offload", "high", "negative", "none", "medium", "planned", "both",
              "Park optimizer states / inactive layers in CPU RAM (or disk) and stream to GPU → fit models "
              "far larger than VRAM, at a latency cost. The 100+GB freed storage helps here."),
    Technique("activation-sparsity", "Pruning / sparsity", "medium", "medium", "medium", "high", "planned",
              "both", "Drop near-zero weights/heads. Ternary already yields free sparsity (zeros)."),
    Technique("distillation", "Knowledge distillation", "medium", "medium", "low", "medium", "planned",
              "training", "Train our small student on a big teacher's outputs (Claude / aria-distiller) → "
              "punch above the student's size. Data, not hardware, is the lever — eased by 100+GB storage."),
    Technique("subquadratic-attn", "Sub-quadratic / windowed attention", "medium", "high", "low", "high",
              "planned", "both", "Replace O(T²) attention with windowed/linear variants → longer context "
              "on the same VRAM."),
    Technique("quantum-coproc", "Quantum brain as cheap co-processor", "low", "low", "none", "low", "built",
              "inference", "The pure-Python PEIG brain conditions generation at ~0.5ms/token, no GPU. A free "
              "conditioning signal (off by default until A/B-vindicated — see aria_lm/fusion.py)."),
]


def catalog() -> list[dict]:
    """The full technique catalog as plain dicts."""
    return [t.to_dict() for t in CATALOG]


def by_status(status: str) -> list[dict]:
    return [t.to_dict() for t in CATALOG if t.status == status]


def stack_for_inference() -> list[str]:
    """The recommended inference frugality stack (biggest honest wins first)."""
    return ["ternary-bitnet", "int8-quant", "cpu-offload", "quantum-coproc"]


def stack_for_training() -> list[str]:
    """The recommended training frugality stack on 8GB."""
    return ["mixed-precision", "grad-checkpoint", "grad-accum", "qlora", "distillation"]
