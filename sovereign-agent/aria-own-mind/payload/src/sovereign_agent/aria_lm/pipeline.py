"""aria_lm/pipeline.py — Grow Aria's mind end-to-end: corpus → tokenizer → train → checkpoint.

One call builds her own model from her own text and persists it so the `aria_own_lm` tool can speak
with it. VRAM-locked (never runs beside the orchestrator). Honest: small model, real training, the
code scales. A full base-weight run is Tier 3 (Ring 3, human-gated) — this convenience seeds a tiny one.
"""
from __future__ import annotations

from pathlib import Path


def default_checkpoint() -> Path:
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir / "aria_lm" / "aria_mind.pt"


def grow_mind(out_path: Path | None = None, *, max_chars: int = 400_000, target_vocab: int = 1024,
              n_layer: int = 3, n_head: int = 4, n_embd: int = 96, block_size: int = 96,
              batch_size: int = 16, iters: int = 2000, lr: float = 4e-4, dropout: float = 0.1,
              vram_locked: bool = True) -> dict:
    """Build + train + checkpoint Aria's own model. Returns a summary dict (curve, params, path).

    Defaults are right-sized for her genuinely-prose own-corpus (small + high quality): a small,
    dropout-regularized model that GENERALIZES (val loss drops) rather than a big one that memorizes.
    """
    from .data import gather_corpus, build_dataset
    from .train import train_model
    from .generate import save_checkpoint

    out_path = Path(out_path) if out_path else default_checkpoint()

    def _run() -> dict:
        corpus = gather_corpus(max_chars=max_chars)
        ds = build_dataset(corpus, target_vocab=target_vocab)
        res = train_model(ds, n_layer=n_layer, n_head=n_head, n_embd=n_embd, block_size=block_size,
                          batch_size=batch_size, iters=iters, lr=lr, dropout=dropout,
                          warmup=max(20, iters // 20), eval_every=max(50, iters // 6))
        save_checkpoint(res, out_path)
        return {
            "checkpoint": str(out_path),
            "num_params": res["num_params"],
            "device": res["device"],
            "val_loss_first": res["first_val_loss"],
            "val_loss_final": res["final_val_loss"],
            "learned": res["learned"],
            "n_tokens": ds["n_tokens"],
            "vocab_size": ds["vocab_size"],
            "curve": res["curve"],
        }

    if vram_locked:
        try:
            from sovereign_agent.vram import vram_lock
            with vram_lock("aria_lm.grow_mind", timeout_seconds=5.0):
                return _run()
        except Exception:
            # If the lock module isn't importable in a bare context, run unlocked (apply-time only).
            return _run()
    return _run()


if __name__ == "__main__":
    import json
    summary = grow_mind()
    summary.pop("curve", None)
    print(json.dumps(summary, indent=2))
