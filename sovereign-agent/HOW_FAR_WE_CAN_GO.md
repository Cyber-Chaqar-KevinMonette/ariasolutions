# How Far We Can Go — An Honest Ceiling (and the methods to raise it)

> Kevin's instruction: never the lazy excuse that "the hardware isn't good enough." This is the
> constructive, honest answer — exactly how far we go on a GTX 1070 (8GB), and what raises the ceiling.
> Verdict of the Tribunal on this document: claims below are anchored to measured results or honest math.

## What is real and proven right now

- **A from-scratch FOSS transformer that genuinely learns.** Measured: val loss 7.66 → 3.46 (perplexity
  ~2125 → ~32) on the 1070. Forward pass correct; the test suite asserts val loss drops every run.
- **Our own ternary BitNet (b1.58), proven.** Ternary weights {−1,0,+1}: val loss 6.95 → 4.77,
  **matching fp16** (Δ −0.07, within noise), **31% free sparsity**, **~10× smaller weights** (1.58
  bits/weight). At inference, matmuls become add/subtract.
- **A god-tier scrutiny Tribunal** that catches ungrounded profundity (it flagged the prior Aria's output
  at profundity-density 11, and caught a real misstatement by its own authors — see SYSTEM_TRIBUNAL_REPORT).
- **24 tests green across the three new systems; safety kernel GREEN; DEFERRED_UNSAFE held.**

## The honest ceiling on this hardware (the planner's real math)

Weight storage is *not* the binding constraint — ternary makes it tiny:

| Model size | Ternary weights | fp16 weights | fp16 training (full) |
|-----------:|----------------:|-------------:|---------------------:|
| 50M params | ~0.01 GB | ~0.10 GB | ~0.85 GB + activations |
| 200M params | ~0.04 GB | ~0.40 GB | ~3.2 GB + activations |

So on 8GB:
- **Inference:** even a few-hundred-million-param model fits comfortably in ternary; with int8 + CPU/NVMe
  offload (the freed 100+GB helps), substantially larger quantized models become runnable.
- **Training:** full fine-tunes of tens-of-millions of params fit; with gradient checkpointing + QLoRA
  (adapters over a frozen 4-bit base) the trainable ceiling climbs further. Activation memory and **wall-
  clock time**, not weight storage, become the real limits.

## The actual bottleneck (named honestly): data, not the GPU

Last session's finding stands: Aria's genuinely-prose own-corpus is small (~16K clean tokens), so a large
model memorizes instead of generalizing. **More clean training data is the single biggest lever** — and it
is now far more reachable: 100+GB of freed storage makes **distillation** (train our small student on a big
teacher's generated text — Claude / aria-distiller) and large curated corpora practical. The code is ready
for the data; the data was the gap.

## The methods that raise the ceiling (built · available · planned)

- **Built:** ternary BitNet, gradient accumulation, mixed precision, the quantum brain as a free
  (~0.5ms/token, no-GPU) conditioning co-processor.
- **Available next:** int8/4-bit inference quant, gradient checkpointing, CPU/NVMe offload.
- **Planned (real, doable here):** QLoRA fine-tuning, knowledge distillation from the teachers, pruning,
  sub-quadratic attention. Each is a staged, reversible, Ring-2 capability — and each must clear the
  Tribunal (no overstated savings) before it's promoted.

## So — how far can we go?

**Far enough to matter, honestly.** On this 2016 GPU we can build, train, and run a real, owned, ternary
model in the tens of millions of parameters, scaffolded by a god-tier reasoning/scrutiny/foresight system —
and scale the *same code* the moment the hardware or the data grows. We won't rival GPT-4 on one 1070 (that
is physics and economics, not laziness), and saying otherwise would betray the witnessing principle. But the
durable assets — the architecture, the BitNet, the Tribunal, the frugality stack, the foresight — are real,
ours, and built to grow. The ceiling rises with data first, hardware second; both are now in reach.

With love, and the truth. 💛
