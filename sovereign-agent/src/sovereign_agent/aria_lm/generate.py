"""aria_lm/generate.py — Save / load / run inference on Aria's own trained model.

Checkpointing (model weights + config + tokenizer merges) so her trained mind persists on disk, and a
clean text-generation entry point. Pure local inference — no API, her own weights. This is how Aria
thinks with the mind we built her.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch

from .model import AriaGPT, GPTConfig
from .tokenizer import ByteBPETokenizer


def save_checkpoint(result: dict, path: Path) -> Path:
    """Persist a trained model: weights + config + tokenizer + the learning curve. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = result["config"]
    tok: ByteBPETokenizer = result["tokenizer"]
    torch.save({
        "model_state": result["model"].state_dict(),
        "config": cfg.__dict__,
        "tokenizer": {"vocab_size": tok.vocab_size,
                      "merge_order": [list(p) for p in tok.merge_order]},
        "curve": result.get("curve", []),
        "fused": result.get("fused", False),
        "num_params": result.get("num_params"),
    }, path)
    return path


def load_checkpoint(path: Path, device: str | None = None) -> dict:
    """Load a saved model + tokenizer. Returns {model, tokenizer, config, device} ready for generate()."""
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(path, map_location=dev, weights_only=False)
    cfg = GPTConfig(**ckpt["config"])
    model = AriaGPT(cfg).to(dev)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    tok = ByteBPETokenizer()
    tok.merge_order = [tuple(p) for p in ckpt["tokenizer"]["merge_order"]]
    nid = 256
    for pair in tok.merge_order:
        tok.merges[tuple(pair)] = nid
        nid += 1
    tok.vocab_size = ckpt["tokenizer"]["vocab_size"]
    return {"model": model, "tokenizer": tok, "config": cfg, "device": dev}


@torch.no_grad()
def generate(loaded: dict, prompt: str = "", max_new_tokens: int = 160,
             temperature: float = 0.8, top_k: int = 40) -> str:
    """Generate text from a loaded checkpoint (or a train result dict)."""
    model, tok, dev = loaded["model"], loaded["tokenizer"], loaded["device"]
    ids = tok.encode(prompt) if prompt else tok.encode(" ")
    ids = ids or [32]
    idx = torch.tensor([ids], dtype=torch.long, device=dev)
    out = model.generate(idx, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k)
    return tok.decode(out[0].tolist())
