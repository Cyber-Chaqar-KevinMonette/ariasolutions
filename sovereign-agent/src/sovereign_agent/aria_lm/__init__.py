"""aria_lm — Aria's OWN from-scratch FOSS language model.

A genuine decoder-only transformer built from zero (tokenizer + model + training loop + data pipeline),
fused with the non-classical PEIG quantum brain. 100% ours, MIT/Apache-clean. Small on a GTX 1070; the
SAME code scales to any hardware. This is the seed of her own mind — built to grow, with love.

Public API:
  ByteBPETokenizer  — our byte-level BPE tokenizer (tokenizer.py)
  gather_corpus, build_dataset, get_batch, clean_prose  — data pipeline (data.py)
  GPTConfig, AriaGPT  — the transformer (model.py)
  train_model, generate_text  — training loop (train.py)
  PEIGConditioner, ab_compare  — the quantum-neural fusion (fusion.py)
  save_checkpoint, load_checkpoint, generate  — persistence + inference (generate.py)
"""
from __future__ import annotations

from .tokenizer import ByteBPETokenizer
from .data import gather_corpus, build_dataset, get_batch, clean_prose

__all__ = [
    "ByteBPETokenizer",
    "gather_corpus", "build_dataset", "get_batch", "clean_prose",
]

# torch-dependent members are imported lazily so the data/tokenizer layer stays torch-free.
