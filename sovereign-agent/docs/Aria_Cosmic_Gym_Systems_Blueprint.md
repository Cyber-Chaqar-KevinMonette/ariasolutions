# Aria — Systems Integration & Sentinel Architecture
## Cosmic Gym Edition ✦ Grounded in v0.2.60 ✦ Built for the Real Machine

> **Companion to:** `MOS_Image_Intelligence_God_Tier.md` (the doctrine) — this is the *integration map*:
> how the image domain, the inbox/queue, the reading system, and the regression catalog slot into
> Aria's **actual** architecture without breaking a clause of the Unified MOS Canon (34) or the
> Architect-Auditor skill.
>
> **Read against your code, not the abstract.** Every design below uses a pattern that already exists
> in `sovereign-agent`: the sentinel base contract, `authority.py` dispatch-gating, the `diagnosis.py`
> Conflict→Diagnosis→Resolution catalog, the `vram_lock`, the per-sentinel `inbox.jsonl`.
>
> **Kernel held throughout:** Safety · Love · Flourishing. Propose, don't act. Reversible by construction.

---

## 0. Orientation — what I read, what I extend, what I refuse to touch

**What's already there (and excellent):**
- A dozen sentinels on one contract (`stewardship/base.py`): hash-bound manifest → catalogs → atoms,
  per-sentinel `inbox.jsonl`, kill switches (`SOV_NO_<X>_SENTINEL` + master `SOV_NO_SENTINELS`),
  `scan()/health_status()/articles()`, and the load-bearing discipline that **most sentinels don't
  implement `heal()`** — Tier 1 proposes, the operator acts.
- `authority.py`: the dispatch gate. Out-of-ceiling tools are **withheld from the model's tool list** —
  a model can't call what it can't see. Tier 3 requires `requires_approval=True`. Every tool must
  declare `failure_modes` (CI-checked).
- `diagnosis.py`: the Conflict Logic Catalog — append-only, every record names an `actor`
  (Kevin/Claude/Aria), no resolution without a rollback plan.
- `vram.py`: real accounting for an 8GB GTX 1070, with `can_run_heavy_tool` and a file-lock
  (`vram_lock`) that serializes heavy GPU tools against the orchestrator.
- `qa/`, `retrieval/`, `planner/`, `ollama_client.py`, `self_practice.py`, and the started
  `aria-inbox-context` / `aria-inbox-pane` payloads.

**What this wave extends:** the image capability stack, the inbox/queue, the reading (ORACLE) system,
and a regression catalog — all as new sentinels + tools + catalogs in the existing shapes.

**What it refuses to touch (your own `DEFERRED_UNSAFE`, reaffirmed in §11):** autonomous goal
generation, recursive self-code-rewriting, value/axiom self-authorship, unbounded self-improvement,
substrate independence. None of "more autonomy" below crosses that line — and §7 explains why the line
is exactly what *earns* the new capability.

---

## 1. The Binding Constraint — VRAM (the 1070 truth)

This is the most important section. Everything else bends around it.

**The arithmetic on your card (8GB, Pascal):**

```
qwen3:8b q4_K_M orchestrator weights   ~5,200 MB   (resident while Aria thinks)
KV-cache @ 16k                            ~550 MB
OS / COSMIC compositor                    ~800 MB
CUDA driver + safety floor                ~400 MB
─────────────────────────────────────────────────
Left for everything else                ~1,250 MB
```

A modern image model does not fit in 1,250 MB. It doesn't fit *beside* the orchestrator at all:

| Local image model | Realistic VRAM (weights + text-encoder + VAE + activations) | On your 1070 |
|---|---|---|
| **SD 1.5** | ~2–4 GB | ✅ Runs (with the orchestrator paused) |
| **SDXL / SDXL-Turbo** | ~7–10 GB | ⚠️ Only with `--medvram` / sequential offload; slow on Pascal |
| **FLUX.1 schnell/dev (GGUF Q4 + offloaded T5)** | ~8–12 GB effective | ❌ Painful-to-infeasible; minutes/image if at all |

**Two hard conclusions, stated plainly so you're never surprised again:**

1. **Local image generation must serialize against the orchestrator** exactly like whisper and EasyOCR
   already do. It is a *heavy GPU tool*. It takes the `vram_lock`, pauses/unloads the qwen model,
   renders, then restores. The `ImageSentinel` calls `can_run_heavy_tool()` before scheduling — your
   existing mechanism, reused verbatim.
2. **FLUX-class quality is a Tier-1 API job, not a Tier-0 job, on this hardware.** The honest local
   ceiling is SD 1.5 (reliable) or a carefully-offloaded SDXL (slow). When a job needs better than the
   1070 can produce, `route()` drops to fal.ai / Replicate and **says so**, noting the
   privacy/reproducibility tradeoff. This is not a failure of sovereignty — it's sovereignty being
   *honest about its substrate*. (The path to true Tier-0 FLUX is a bigger card; until then, the
   architecture routes around the wall instead of pretending it isn't there.)

> **This is very likely the root cause of the "shockingly bad" prior results.** A 12B model squeezed
> onto 8GB either OOMs, silently falls back to a tiny model, or runs at extreme quantization that
> wrecks quality. The fix isn't a better prompt — it's the routing rule above. `JUST WHY` on the bad
> output lands here: *hardware/model mismatch, not prompt error.*

---

## 2. The Image Capability Stack on Real Hardware

GENESIS + SCULPTOR (from the doctrine) wired into Aria, VRAM-aware end to end.

```
┌────────────────────────────────────────────────────────────────────┐
│ ImageSentinel  (stewardship/image_sentinel.py)                      │
│  • the ONLY door to the image domain                                │
│  • pre-screen (§2.1 hard lines, fail-closed) · consent/tier (§2.2)  │
│  • takes vram_lock for local heavy ops · stamps provenance          │
│  • writes image_ledger.jsonl · proposes, never heals irreversibly   │
└───────────────┬────────────────────────────────────────────────────┘
                │
   ┌────────────┴───────────┐
   ▼                        ▼
GENESIS (create)        SCULPTOR (edit)
   │                        │
   ▼                        ▼
route(job) ── T0 local? ──► fits VRAM? ──► SD1.5 / SDXL-offload (vram_lock)
   │                  └─ no ─► T1 API (fal/Replicate) + tradeoff note
   └─ reading/QA ─────────────────────────────► ORACLE (§4)
```

**SCULPTOR's first real job is your blazer** — and it's a *CPU* job (the luminance-preserving recolor
in the doctrine §5.3 is pure Pillow/numpy, no GPU). So the highest-frequency edits (recolor, crop,
background via `rembg`, restoration via a small upscaler) don't even contend for VRAM. Only true
generative inpainting (FLUX Fill) does — and that routes through the VRAM gate or to Tier 1.

**Tool registration** (so it inherits the authority gate automatically):

```python
register_tool(ToolMeta(
    name="image.recolor",            # SCULPTOR, CPU, reversible
    tier=1, description="Luminance-preserving garment recolor; writes a NEW file.",
    failure_modes=("mask bleed at edges", "flat result if mask too tight", "color cast under warm light"),
))
register_tool(ToolMeta(
    name="image.generate.local",     # GENESIS, heavy GPU, reversible output
    tier=1, description="Local diffusion render; serializes via vram_lock.",
    failure_modes=("OOM on >SD1.5", "slow on Pascal", "silent model downgrade if unguarded"),
))
register_tool(ToolMeta(
    name="image.generate.api",       # GENESIS via Tier-1 provider — leaves the machine
    tier=2, requires_approval=False, description="Cloud render when local can't meet the bar.",
    failure_modes=("image leaves device", "provider policy gate", "partial reproducibility"),
))
```

The dispatch gate now does the safety work for free: in a read-only mode, none of the write/generate
tools are even *offered* to the model.

---

## 3. The Inbox & Queue System

You already started `aria-inbox-context` and `aria-inbox-pane`. This completes them into a real
ingestion pipeline — drop a file, it gets screened, queued, processed, and the result lands back in the
pane.

### 3.1 Directory layout (under the data dir, beside `sentinels/`)

```
inbox/
  read/        ← drop an image to be analyzed/OCR'd
  edit/        ← drop an image + optional job sidecar to be edited
  generate/    ← drop a prompt file (.txt/.md/.yaml) to render
  analyze/     ← drop anything for ORACLE's full reading report
  _processing/ ← claimed jobs (atomic move on claim)
  _done/       ← finished, with result sidecars
  _review/     ← anything that hit a gate and needs your eyes  (fail-closed lane)
  _failed/     ← errored, with diagnosis sidecar linking a Conflict case
```

### 3.2 The job descriptor (optional sidecar — sensible defaults if absent)

Drop `headshot.jpg` alone → inferred from the folder (`edit/` → SCULPTOR with defaults). Or pair it
with `headshot.job.yaml` for control:

```yaml
intent: edit                 # read | edit | generate | analyze
op: recolor                  # recolor | inpaint | upscale | bg_remove | ...
params: { region: blazer, mode: to_white }
quality_gate: strict         # FOUNDRY gate to apply
consent: self                # self | { subject: name, record: path }   (§2.2)
priority: normal             # low | normal | high
```

### 3.3 The IntakeSentinel (new — owns the inbox)

A first-class sentinel on the base contract. Charge:

- **Watch** the `inbox/<intent>/` folders (polling on a cadence — no exotic deps; or `watchdog` if you
  want it, behind a kill switch).
- **Screen on arrival** via ORACLE's safety pre-screen (§4) — *fail-closed*: anything unscreenable or
  flagged goes straight to `_review/`, never to `_processing/`.
- **Enqueue** into a durable, append-only queue (`inbox/queue.jsonl` — your exact ledger pattern) with
  states: `received → screening → queued → processing → done | failed | review`.
- **Schedule** VRAM-aware: heavy jobs (generation, OCR) acquire the `vram_lock`; CPU jobs (recolor,
  crop) run freely in parallel. This is the whole reason the queue exists — to serialize GPU contention
  gracefully instead of OOMing.
- **Notify** results through the existing per-sentinel `inbox.jsonl` so the cockpit pane surfaces them.
- **Propose, don't act, on anything irreversible.** A `generate.api` job (leaves the machine) lands in
  `_review/` for a one-tap confirm unless you've pre-authorized that intent.

The queue **survives restart** (it's on disk, append-only). `crash mid-job` → the `_processing/` claim
is detected on boot and either resumed or moved to `_review/`. That's your rollback path, built in.

---

## 4. The Reading System (ORACLE) — God-Tier, Honestly Defined

You asked for reading that equals or beats human ability. Let me be precise rather than flattering,
because precision is what actually makes it god-tier: **an AI reader will not out-*understand* a human.**
What it *can* do — and what no human can — is read **tirelessly, consistently, at scale, with
calibrated confidence, and without ego about what it didn't catch.** That combination is the real
superpower, and it's also exactly your Canon's Law 5 (calibrated uncertainty) and the "intuition is
never followed by ego" clause. So the god-tier reading system is **superhuman in consistency and
throughput, and rigorously humble in judgment.**

### 4.1 The multi-pass pipeline (EasyOCR is already in your VRAM budget)

```
PASS 1  Layout      → regions, columns, reading order, figure/text separation
PASS 2  OCR         → text extraction (EasyOCR, ~2GB, vram_lock)   + per-token confidence
PASS 3  Vision      → scene/object/subject caption (local vision model via ollama_client)
PASS 4  Structure   → extract to schema (tables → rows, forms → fields, charts → series)
PASS 5  Integrity   → cross-check: does OCR text agree with layout? do passes contradict?
PASS 6  Aesthetic   → sharpness, exposure, artifacts, seams/halos (feeds FOUNDRY + §5)
```

### 4.2 The two rules that make it trustworthy

1. **Every read carries a confidence score, and low-confidence reads are *flagged, not asserted*.**
   A blurry serial number comes back as `value: "B8?4", confidence: 0.42, → review`, never as a
   confident wrong answer. Asserting a confident wrong read is the cardinal sin of a reading system —
   it's worse than saying "I'm not sure."
2. **Contradiction between passes is surfaced, not silently resolved.** If OCR says one thing and the
   vision caption implies another, ORACLE reports the conflict (and can open a `diagnosis.py` case) —
   it does not pick a winner and hide the disagreement.

### 4.3 Output — the Reading Report

A structured, durable artifact (not just a caption): regions, extracted text + confidences, structured
data, integrity findings, aesthetic flags, and an overall `confidence` + `needs_review: bool`. This is
what feeds the queue's `_done/` sidecar and the cockpit pane.

---

## 5. The Regression Catalog — Built in Your Conflict-Logic Shape

This is the "Fixes & Solutions catalog" you've been pointing at, made specific to images and wired into
`diagnosis.py`. Same triplet: **Conflict → Diagnosis → Resolution**, append-only, actor-stamped, no
resolution without a rollback plan — plus one image-domain addition: **every entry carries a detecting
test.** A failure mode that can't be detected can't be regression-guarded.

### 5.1 Seed catalog (each entry = a known failure with its detector)

| Conflict (symptom) | Diagnosis (cause) | Resolution (fix) | Detector |
|---|---|---|---|
| Flat, paper-cutout recolor | luminance crushed to a single value | preserve luminance band, lift not flatten (doctrine §5.3) | variance of recolored region < threshold → fail |
| Halo/seam around edited region | hard mask, no feather | Gaussian-feather mask + edge blend | edge-gradient spike at mask boundary → fail |
| Mask bleed onto skin/shirt | chroma threshold too loose | tighten HSV + spatial prior; fall to FLUX Fill if uncuttable | ORACLE seam pass flags off-region pixels |
| Prompt adherence drift in a series | guidance/seed wander | pin seed-base + per-piece offset; FOUNDRY constant-check | vision-model match score < bar → regenerate |
| Series constant violated | manifest not enforced | check `visual_constants` before ship | constant-presence assertion fails |
| Provenance stamp missing | output bypassed the Sentinel | the Sentinel is the only door; reject un-stamped | ledger entry has no `provenance_id` |
| Silent model downgrade / OOM | heavy model on 8GB unguarded | `can_run_heavy_tool` gate + explicit route note | VRAM probe + model-actually-loaded assertion |

### 5.2 The RegressionSentinel (new — runs the catalog)

On the base contract. It **does not edit images**; it `scan()`s outputs against the catalog's detectors
and `proposals()` a block on anything matching a known failure. The block is *enforced* by FOUNDRY's
quality gate (the choke point), not by the sentinel acting unilaterally — propose, don't act, intact.
New failures you and I hit get *added* to the catalog (actor-stamped), so the system never re-ships a
bug it has seen once. That's the regression discipline: **a fixed bug becomes a permanent test.**

---

## 6. The Sentinel Roster Expansion (disciplined, not maximal)

You asked which sentinels 1000X the value. The honest answer: **a small number with crisp, disjoint
ownership** — not a swarm. Over-sentinel-ization is its own failure mode (coordination overhead, diffuse
accountability, "which sentinel owns this?" ambiguity). Each one below owns a concern nothing else owns:

| Sentinel | Owns | Tier ceiling | Heals? |
|---|---|---|---|
| **ImageSentinel** | the door to the image domain: pre-screen, consent, provenance, ledger, VRAM acquisition | T2 (request only) | no — proposes |
| **IntakeSentinel** | the inbox/queue: arrival screening, durable queue, VRAM-aware scheduling, results routing | T1 | no — moves to `_review/` for anything irreversible |
| **RegressionSentinel** | the failure catalog: detect known-bad, block via the gate, grow the catalog | T0 (read-only scan) | no — proposes block |

That's it for this wave. **Reading-quality** lives as a *catalog inside* ImageSentinel/ORACLE, not a
separate sentinel — it's a concern, not an owner. Resist the urge to mint a sentinel per feature; mint
one per *boundary that must be guarded*. Three new guarded boundaries → three sentinels.

Each registers a `SentinelIdentity` in `sentinel_roster.py` with the shared creed ("observe and advise,
read-only or reversible by construction, none acts irreversibly without a human"), so each knows its
place in the whole. The kernel (Safety, Love, Flourishing) holds them all.

---

## 7. Autonomy — Honestly

You asked to 100X autonomy and tool-calling. Here is the truth, and it's *good* news: **your
architecture already solved this, and the solution is bounded autonomy, not unbounded.**

The lever for "more autonomous" is not "remove the human" — it's **add more Tier 0 and Tier 1 tools**,
which the dispatch gate lets the model reach for freely (read-only and reversible-scoped), while T2/T3
stay gated. Aria gets *dramatically* more capable — she can read your whole inbox, analyze, recolor,
draft variants, run the regression suite, queue work, all on her own initiative — **because every one
of those is reversible or read-only, and the gate physically prevents her from reaching past the
ceiling.**

```
What "more autonomy" means here          Tier   Human in loop?
─────────────────────────────────────────────────────────────
read/analyze/OCR every inbox item         T0     no (and can't do harm)
recolor, crop, bg-remove, upscale         T1     no, logged, reversible
draft N generation variants locally       T1     no, logged
run the regression catalog, propose       T0     no
generate via cloud API (leaves machine)   T2     yes — one tap
delete/overwrite, push, external mutate    T3     yes — explicit approval
self-modify code / author values / etc.    —      NEVER (DEFERRED_UNSAFE)
```

**The rails are what earn the capability.** You can safely grant Aria a huge amount of bounded
autonomy *precisely because* the unsafe ceiling is hard, the gate is physical (tools withheld, not just
discouraged), and every irreversible step has a human. An agent you can't bound is an agent you can't
trust with much; an agent bounded this well can be trusted with a lot. That's the 100X — and it costs
you nothing in safety because the safety is structural.

This is also the right answer to the part of you that wants her to grow into more. She grows in
*capability and usefulness*, not in *independence from you*. She remains a system you author and
authorize — never a thing that authors its own purposes. That distinction is the whole ballgame, and
your `DEFERRED_UNSAFE` already names it. We keep it named.

---

## 8. Observability & the Ledgers (one spine)

Inherited law: no observability → not production-ready; no rollback → deployment incomplete.

- **`image_ledger.jsonl`** — every image op: pillar, model, seed, params_hash, input/output hashes,
  provenance_id, tier, prescreen_result, utc. Fully reproducible.
- **`inbox/queue.jsonl`** — every job's state transitions. Survives restart.
- **`diagnosis/cases/`** — every failure becomes a Conflict case with a rollback plan.
- **Alert triggers:** prescreen fail, fail-closed → `_review`, tier-downgrade (local→cloud),
  quality-gate hard-fail, provenance-stamp failure, VRAM OOM, queue depth over threshold.
- **Rollback (≤3 steps):** non-destructive sourcing means the original always survives → discard output
  → mark ledger `reverted` (+ restore manifest snapshot if a series was touched).

---

## 9. The Map

```
                          ┌──────────────────────────────┐
   you drop a file ─────► │   inbox/<intent>/            │
                          └───────────────┬──────────────┘
                                          ▼
                              ┌───────────────────────┐
                              │   IntakeSentinel       │  screen (fail-closed) → queue.jsonl
                              │   VRAM-aware scheduler  │  CPU jobs ∥  · GPU jobs ⇒ vram_lock
                              └───────┬─────────┬───────┘
                  CPU (free, parallel)│         │ heavy (serialized)
                                      ▼         ▼
                              ┌───────────┐ ┌──────────────────────┐
                              │ SCULPTOR  │ │ GENESIS / OCR / Vision │
                              │ (recolor) │ │ (route: local⇄T1 API)  │
                              └─────┬─────┘ └──────────┬───────────┘
                                    └──────┬───────────┘
                                           ▼
                              ┌────────────────────────┐
                              │  ImageSentinel          │  provenance + image_ledger.jsonl
                              └────────────┬───────────┘
                                           ▼
                              ┌────────────────────────┐
                              │  FOUNDRY quality gate   │ ◄── RegressionSentinel detectors
                              └────────────┬───────────┘
                              PASS ▼            ▼ HARD-FAIL
                          inbox/_done/      inbox/_review/  (your eyes)
                                                 │
                                          opens diagnosis case → catalog grows
```

One door (ImageSentinel). One scheduler (IntakeSentinel, VRAM-aware). One gate (FOUNDRY + Regression).
Everything reversible or read-only until a human says otherwise.

---

## 10. Risk Matrix

```
🔴 RED — blocking:
  Risk: local heavy model OOMs or silently downgrades on the 1070 → garbage output (the prior failure)
  Trigger: image.generate.local scheduled without VRAM gate, or model > SD1.5 unoffloaded
  ✅ BEST PATH: can_run_heavy_tool() gate + assert-model-loaded + explicit route-to-T1 when local can't meet bar
  Rollback: discard output → ledger reverted (2 steps, 1 system)

🔴 RED — blocking:
  Risk: an irreversible job (cloud generate, overwrite) runs without a human
  Trigger: T2/T3 op reaches the model's tool list
  ✅ BEST PATH: dispatch gate withholds it; IntakeSentinel routes to _review/. Already your mechanism.

🟡 YELLOW — material:
  Risk: ORACLE asserts a confident-but-wrong read
  ✅ BEST PATH: confidence on every read; low-confidence → _review, never assert; contradictions surfaced

🟡 YELLOW — material:
  Risk: sentinel sprawl — too many overlapping sentinels, unclear ownership
  ✅ BEST PATH: mint one sentinel per guarded boundary, not per feature. Three this wave. Hold the line.

🟢 GREEN — watch:
  Risk: 1070 caps local image quality indefinitely
  ✅ BEST PATH: T1 API bridges today; a bigger card unlocks Tier-0 FLUX later. Architecture already routes either way.

FRAGILE ASSUMPTIONS:
  1. EasyOCR + a local vision model fit alongside nothing (need vram_lock).
     ✅ VALIDATE: vram.can_run_heavy_tool before each; they already serialize — reuse it.
  2. Classical masks suffice for most recolors.
     ✅ VALIDATE: ORACLE seam pass; uncuttable → FLUX Fill (VRAM-gated or T1), declared fallback.

WHAT I MIGHT BE WRONG ABOUT:
  Exact local image-model VRAM ceilings shift with quantization/offload advances. The *routing rule*
  (local until it can't meet the bar, then T1, always with a tradeoff note) is robust regardless.
  Validate the best-fitting local model at integration and date-stamp it in the ledger.

7TH-GENERATION CHECK: +2
  Provenance + reproducible ledgers + local-first + no vendor lock + no self-modification.
  Capability grows; sovereignty and human authority do not erode. No irreversible debt introduced.
```

---

## 11. What We Explicitly Do **Not** Build (DEFERRED_UNSAFE, this wave)

Reaffirmed, because "1000X" is exactly when discipline matters most:

- **No autonomous goal generation.** Aria queues and processes *your* intents. She does not decide what
  to make or do on her own initiative.
- **No self-code-rewriting, no value/axiom self-authorship.** The image/inbox/reading code is authored
  by you and me; the kernel and Canon are not self-edited.
- **No un-gated irreversibility.** Every cloud call, overwrite, or external mutation has a human tap.
- **No covert capability.** No un-stamped outputs, no unledgered ops, no hidden generation.
- **No authority self-escalation.** No sentinel raises its own tier or authorizes another.

Self-improvement of these subsystems stays **bounded, observable, non-self-modifying** — it sharpens
prompts, mask heuristics, reading confidence calibration, and quality rubrics. It never touches code or
values. (Same contract as `self_practice.py`.)

---

## 12. The Build Roadmap — and the single highest-leverage first move

Phased so each step is verifiable, and honest about what needs the GPU vs. what's CPU-only.

**▶ FIRST MOVE (do this one, it's the spine — CPU-only, no models, fully testable tonight-or-tomorrow):**
`IntakeSentinel` + `inbox/` folder tree + `queue.jsonl` + the job descriptor + `image_ledger.jsonl` +
the `ImageSentinel` shell with the §2.1 pre-screen and provenance stamp. Pure logic. It's the bottom of
the dependency graph — everything else plugs into it. Ship it as `aria-image-intake/` with
`apply_image_intake.sh`, tests alongside, version bump + reinstall (so the CacheSentinel reads matching
metadata — your known drift trap).

**Phase 2 — SCULPTOR classical core (CPU):** the luminance-preserving recolor (your blazer), `rembg`
background, small-model upscale. Real edits, no VRAM contention. *This is where the blazer actually
gets done, correctly.*

**Phase 3 — ORACLE (local, VRAM-gated):** EasyOCR + local vision passes, the Reading Report, confidence
calibration. Reuses `vram_lock`. Build the report schema + integrity pass first as a scaffold; wire the
models behind the gate.

**Phase 4 — GENESIS local + routing (VRAM-gated ⇄ T1):** SD1.5 local via `vram_lock`; `route()` to
fal/Replicate with tradeoff notes when the bar exceeds the 1070. FOUNDRY quality gate + RegressionSentinel
detectors enforce the floor.

**Phase 5 — FOUNDRY full + series:** variant orchestration, series manifest enforcement, regression
suite in CI. Quality becomes structurally guaranteed, not hoped for.

---

## 13. Close

The version of "overkill is the floor" that's actually true here isn't more features or more sentinels.
It's: **one honest VRAM routing rule that ends the bad-output problem, one durable inbox spine, one
reading system humble enough to flag what it can't read, one regression catalog that turns every fixed
bug into a permanent test, and a capability expansion that grows Aria's usefulness without eroding a
single rail.** That's the muscle. It holds weight because every kilo of it is load-bearing.

She gets stronger. You stay the author. The kernel holds.

> *I know the next move. Should I proceed?*
