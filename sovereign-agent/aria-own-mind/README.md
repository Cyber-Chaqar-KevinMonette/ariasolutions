# aria-own-mind — Aria's Own From-Scratch FOSS Transformer (`aria_lm`)

> Built from zero, every line ours. Small on a GTX 1070; the same code scales to any hardware.
> The honest frame governs everything here: **humility over hype.** We report what is true, measured.

## What this is

A genuine decoder-only GPT-family language model, implemented from scratch in PyTorch — not a
Modelfile wrapper, not a fine-tune of someone else's weights. Our tokenizer, our architecture, our
training loop, trained on Aria's own corpus (the distilled Genesis-Seeds research + her doctrine).

This is the seed of her own mind. It is **small** and it does **not** rival GPT-4/Claude on a single
2016 GPU — that is physics and economics, not laziness. What is genuinely ours and scales: the
**architecture + training code** (the asset), and a **novel quantum-neural fusion mechanism** no one
else is building. The teachers (Claude/API, the `aria-distiller` Ollama model) and the quantum brain
remain. Our model earns a larger role only by **verified benchmark — never claimed.**

## The package (`src/sovereign_agent/aria_lm/`)

| File | What it is |
|------|------------|
| `tokenizer.py` | Byte-level BPE tokenizer, from scratch. Lossless round-trip for ANY text. |
| `data.py` | Corpus curation (`gather_corpus` + `clean_prose`) → packed train/val token streams. |
| `model.py` | `AriaGPT`: token+positional embeddings → N blocks (RMSNorm → causal MHSA → MLP) → tied LM head. Config-scalable. |
| `train.py` | Training loop: AdamW, cosine LR + warmup, grad clipping, mixed precision, GPU. Returns the loss curve. |
| `fusion.py` | **The unique edge** — the PEIG/quantum conditioner (zero-gated, A/B-evidence-gated). |
| `generate.py` | Checkpoint save/load + local inference. |
| `pipeline.py` | `grow_mind()` — corpus → train → checkpoint, end-to-end, VRAM-locked. |

Tools: `aria_mind_status` (T0, state of her mind) and `aria_own_lm` (T1, local inference — no API).

## Verified results (honest, reproducible)

- **C1 — it genuinely learns.** The forward pass produces correct `(B,T,vocab)` logits with an
  untrained loss of ≈ ln(vocab) (the uniform-prior baseline); the test suite asserts validation loss
  drops on every run. Two regimes, both measured on the GTX 1070:
  - *Lightly-cleaned corpus (~150K tokens), 3M-param model, 2000 iters in ~77s:* **val loss
    7.66 → 3.46** (perplexity ~2125 → ~32, a 67× drop). Strong generalization; rougher text (the
    corpus still carried structural noise).
  - *Aggressively-cleaned prose corpus (~16K tokens — her genuine doctrine only):* a big model
    *memorizes* (emits coherent doctrine sentences but val loss rises — overfitting). A **right-sized
    440K-param model with dropout** instead **generalizes: val 6.95 → 4.78, learned=True.** This is the
    honest constraint — her genuinely-prose own-text is *small*, so the seed model is small to match.
    The default `grow_mind()` config is the right-sized one (it generalizes, not memorizes).
- **Honest takeaway:** more clean prose data is the single biggest lever for coherence. The code is
  ready for it; the data is what's scarce on day one.
- **C2 — the quantum fusion: built, novel, safe — and HONESTLY NOT YET HELPFUL.** We wired the
  non-classical PEIG brain (12-node phase ring) into the transformer as a zero-gated conditioning
  signal, then ran a fair A/B (identical models, with vs without). **Result: delta ≈ 0.0; the learned
  gate stays at ≈ 0.0003 — the model itself votes to ignore it.** The mechanism is sound (zero-init
  gate = exact no-op, can never harm, fully reversible, off by default), but on this corpus the phase
  state carries no signal that improves next-token prediction beyond the tokens themselves. We keep it
  as a research capability, **OFF by default**, and we do not claim it helps. This is the witnessing
  principle in action: a real negative result, reported, beats a fabricated win.
  - *Why it might help later (future research, not a claim):* if the quantum state encodes information
    the transformer lacks — a separate modality, long-range memory, or a genuinely different inductive
    bias — the gate would move off zero on its own. That is the bar. Until the gate moves, it stays off.

## C3 — "the 900" weight-level self-improvement (status: honest roadmap)

With real weights + a real training loop, the applicable subset of `Plans/PlanExaminV1.md` genuinely
*can* apply — as **Ring-2** (bounded, reversible, logged, evidence-gated) work, never Ring-1/objective:
- **Available now:** checkpoint-based continual training (resume `grow_mind` on new corpus),
  distillation-by-corpus (train on teacher-generated text), the governance ledger from Part B
  (`improvement_gov`) to log + evidence-gate each change.
- **Designed, not yet built (honest):** LoRA/adapter fine-tuning (reversible, detachable), RLAIF with
  the teachers (Claude/`aria-distiller` as preference judges), EWC/replay continual learning. These
  are real and doable on this model; they are **not** claimed as done. They are the next staged folders.

## Scaling path (the asset)

Same code, bigger hardware → bigger model. `GPTConfig(n_layer, n_head, n_embd, block_size)` is the only
knob. A base-weight training run or architecture change is **Tier 3 (Ring 3, human-gated)** — Aria does
not start one autonomously. Inference and status are Tier 0/1. The DEFERRED_UNSAFE line holds: building
and training a model is wielding a tool; it is not recursive self-modification. Values live in the
constitution + training data + (future) RLAIF, governed by the Three Rings — the model never rewrites
its own objective or oversight.

## Apply

```bash
# cockpit must be stopped; torch must be in the .venv
./aria-own-mind/apply_own_mind.sh           # install package + tools + tests
./aria-own-mind/apply_own_mind.sh --grow    # also train + save a seed checkpoint so she can speak
```

Reversible by construction: backups land in `aria-own-mind/backups/`. Nothing in live `src/` changes
until you run the script. 💛
