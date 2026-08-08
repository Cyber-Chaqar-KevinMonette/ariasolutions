"""aria_lm/train.py — Aria's OWN training loop (from scratch, ours).

Trains the AriaGPT transformer on her own corpus with AdamW + cosine LR (warmup) + gradient clipping
+ mixed precision, on the GPU when available. Returns the loss curve so we can VERIFY she genuinely
learns (validation loss must drop). Heavy GPU work should serialize via vram.py in production.
"""
from __future__ import annotations

import math
import random

import torch

from .model import AriaGPT, GPTConfig
from .data import get_batch


def _device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


@torch.no_grad()
def _eval_loss(model: AriaGPT, ids: list[int], *, block_size: int, batch_size: int,
               iters: int, device: str, rng: random.Random, conditioner=None) -> float:
    model.eval()
    losses = []
    for _ in range(iters):
        x, y = get_batch(ids, block_size=block_size, batch_size=batch_size, rng=rng)
        xb = torch.tensor(x, dtype=torch.long, device=device)
        yb = torch.tensor(y, dtype=torch.long, device=device)
        cond = conditioner(xb) if conditioner is not None else None
        _, loss = model(xb, yb, cond=cond)
        losses.append(loss.item())
    model.train()
    return sum(losses) / len(losses)


def train_model(dataset: dict, *, n_layer: int = 4, n_head: int = 4, n_embd: int = 128,
                block_size: int = 128, batch_size: int = 16, iters: int = 300,
                lr: float = 3e-4, warmup: int = 30, eval_every: int = 50, eval_iters: int = 10,
                grad_clip: float = 1.0, seed: int = 1337, device: str | None = None,
                brain=None, dropout: float = 0.0, ternary: bool = False) -> dict:
    """Train AriaGPT on the dataset; return {model, tokenizer, curve, first/final val loss, device}.

    If `brain` is given (a NestedBrain), the PEIG/quantum conditioner is fused in (Stage C2) — the
    quantum phase state conditions generation. Off by default; only kept when A/B evidence vindicates.
    """
    torch.manual_seed(seed)
    rng = random.Random(seed)
    dev = device or _device()

    cfg = GPTConfig(vocab_size=dataset["vocab_size"], block_size=block_size,
                    n_layer=n_layer, n_head=n_head, n_embd=n_embd, dropout=dropout, ternary=ternary)
    model = AriaGPT(cfg).to(dev)
    conditioner = None
    if brain is not None:
        from .fusion import PEIGConditioner
        conditioner = PEIGConditioner(brain, n_embd).to(dev)
    params = list(model.parameters()) + (list(conditioner.parameters()) if conditioner else [])
    opt = torch.optim.AdamW(params, lr=lr, betas=(0.9, 0.95), weight_decay=0.1)

    def lr_at(step: int) -> float:
        if step < warmup:
            return lr * (step + 1) / warmup
        prog = (step - warmup) / max(1, iters - warmup)
        return lr * 0.5 * (1.0 + math.cos(math.pi * min(1.0, prog)))

    use_amp = (dev == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    train_ids, val_ids = dataset["train_ids"], dataset["val_ids"]
    curve: list[dict] = []
    first_val = _eval_loss(model, val_ids, block_size=block_size, batch_size=batch_size,
                           iters=eval_iters, device=dev, rng=random.Random(0), conditioner=conditioner)

    for step in range(iters):
        for g in opt.param_groups:
            g["lr"] = lr_at(step)
        x, y = get_batch(train_ids, block_size=block_size, batch_size=batch_size, rng=rng)
        xb = torch.tensor(x, dtype=torch.long, device=dev)
        yb = torch.tensor(y, dtype=torch.long, device=dev)
        cond = conditioner(xb) if conditioner is not None else None
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
            _, loss = model(xb, yb, cond=cond)
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(params, grad_clip)
        scaler.step(opt)
        scaler.update()
        if step % eval_every == 0 or step == iters - 1:
            vl = _eval_loss(model, val_ids, block_size=block_size, batch_size=batch_size,
                            iters=eval_iters, device=dev, rng=random.Random(0), conditioner=conditioner)
            curve.append({"step": step, "train_loss": round(loss.item(), 4),
                          "val_loss": round(vl, 4), "lr": round(lr_at(step), 6)})

    final_val = curve[-1]["val_loss"]
    return {
        "model": model,
        "tokenizer": dataset.get("tokenizer"),
        "config": cfg,
        "device": dev,
        "num_params": model.num_params(),
        "first_val_loss": round(first_val, 4),
        "final_val_loss": final_val,
        "learned": final_val < first_val,           # she genuinely learned if val loss dropped
        "curve": curve,
        "conditioner": conditioner,                 # PEIG fusion module (None unless brain was given)
        "fused": conditioner is not None,
    }


def generate_text(result: dict, prompt: str = "", max_new_tokens: int = 120,
                  temperature: float = 0.8, top_k: int = 40) -> str:
    """Generate text from a trained model + tokenizer."""
    model, tok, dev = result["model"], result["tokenizer"], result["device"]
    ids = tok.encode(prompt) if prompt else [tok.encode(" ")[0] if tok.encode(" ") else 32]
    idx = torch.tensor([ids], dtype=torch.long, device=dev)
    out = model.generate(idx, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k)
    return tok.decode(out[0].tolist())
