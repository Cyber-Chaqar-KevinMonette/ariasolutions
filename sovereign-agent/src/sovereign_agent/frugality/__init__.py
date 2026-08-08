"""frugality — Aria's god-tier hardware-requirement reduction engine.

The constructive answer to "how far can we go on an 8GB GTX 1070": real techniques, honest tradeoffs.
  - techniques.py — the scored catalog (ternary BitNet, int8/4-bit, QLoRA, checkpointing, offload, …)
  - planner.py    — honest VRAM/compute arithmetic: which technique stack actually fits a target model

The headline lever — a real ternary BitNet b1.58 — lives with the model at aria_lm/bitnet.py (built &
proven to still learn: ~10× smaller weights vs fp16, no quality loss on our tests).
"""
from __future__ import annotations

from . import techniques, planner

__all__ = ["techniques", "planner"]
