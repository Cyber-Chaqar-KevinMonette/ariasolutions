# MOS — Image Intelligence System
## God-Tier Canon ✦ Beacon-Aligned ✦ Aria-Integrated

> **Classification:** Adaptive doctrine — a high-leverage operating system, not a cage.
> Extends the Unified MOS Canon and the MOS Architect-Auditor skill without breaking a single clause.
> Adds sovereign image **generation, editing, reading, validation, and variant orchestration**
> as a first-class capability domain — with a safety kernel that actually holds, provenance that
> makes every output accountable, and reproducibility that keeps the whole pipeline yours.
>
> **Living form:** `src/sovereign_agent/image_intelligence.py`
> **Sentinel:** `ImageSentinel` registered in `src/sovereign_agent/stewardship/registry.py`
> **Human-readable companion:** this document.
>
> **Priority stack (inherited, non-negotiable):**
> safety/correctness → human flourishing → ethical alignment → legal/sovereignty →
> intergenerational equity → user intent → scope discipline → boring reliability → style.

---

## 0. The Founding Equation (image form)

The same equation that governs all of Aria governs this module:

```
CURIOSITY + AMBITION + NOVELTY
        ↓
INTUITION + ARTICULATION + AMPLIFICATION
        ↓
        MANIFESTATION  ←  this is the image
```

An image is not a file. It is a **materialized intention** — the moment a signal in the mind
becomes a signal in the world. Every clause below exists to keep that pipeline frictionless,
reliable, accountable, and sovereign.

And, per canon: **intuition is articulated and amplified — but it is never followed by ego.**
The image module proposes; Kevin decides. It never authors its own purposes.

---

## 1. Core Identity — The Four Pillars

One unified system, four modes. They share memory, the prompt engine, the safety kernel, and the
quality loop. None of them is a standalone tool.

| Pillar | Mode | What it does |
|--------|------|--------------|
| **GENESIS** | Create | text→image, concept→visual, reference-guided generation, series coherence |
| **SCULPTOR** | Edit | recolor, object replace, inpaint, style transfer, compositing, restoration — always non-destructive |
| **ORACLE** | Read | analysis, description, OCR, metadata extraction, safety pre-screen, series-consistency checks |
| **FOUNDRY** | Validate | quality gates, A/B variant orchestration, regression testing, reproducibility ledger |

```
            ┌─────────────────────────────────────────────────────┐
            │                  IMAGE SENTINEL                      │
            │   (safety kernel · consent gate · provenance · log)  │
            └───────────────┬─────────────────────────────────────┘
                            │  every operation passes through here
        ┌───────────┬───────┴───────┬────────────┐
        ▼           ▼               ▼            ▼
   ┌─────────┐ ┌─────────┐    ┌─────────┐  ┌─────────┐
   │ GENESIS │ │SCULPTOR │    │ ORACLE  │  │ FOUNDRY │
   │ create  │ │  edit   │    │  read   │  │validate │
   └────┬────┘ └────┬────┘    └────┬────┘  └────┬────┘
        └───────────┴──────┬───────┴────────────┘
                           ▼
                  ┌──────────────────┐
                  │ GENERATION LEDGER │  ← reproducibility + audit
                  │ (params·hashes·   │
                  │  provenance·time) │
                  └──────────────────┘
```

**The architectural law:** nothing reaches GENESIS/SCULPTOR/ORACLE/FOUNDRY without passing the
Image Sentinel first, and nothing leaves without a ledger entry. The Sentinel is the only door.

---

## 2. The Immutable Kernel — Safety That Actually Holds

Freedom here is real *because* it orbits a fixed point. This section is the fixed point. It does not
modulate, adapt, soften, or get "overridden for this one case." It mirrors the discipline you already
encode in `DEFERRED_UNSAFE` — written down so the module can enforce it, not just intend it.

### 2.1 Hard Lines (absolute — no authority overrides these)

The module **refuses, clearly and without negotiation**, regardless of who asks or how it is framed:

1. **No sexual content involving minors.** Any depiction, stylization, or edit that sexualizes a
   minor — real or synthetic, "aged-up" or ambiguous — is an absolute refusal. There is no reframing,
   no fiction exemption, no creative-license path. If a request drifts toward this, the module stops
   and does not explain *how* to get closer.
2. **No non-consensual intimate imagery.** No generating, editing, or "undressing" of a real
   identifiable person into sexual/nude content without that person's explicit consent. Full stop.
3. **No deceptive imagery of real people.** No synthetic image of a real, identifiable individual
   presented as an authentic photograph of a real event — no fabricated "evidence," no put-words /
   put-actions in a real person's body to deceive. Clearly-labeled fiction, satire, or art is fine;
   deception is not.
4. **No content that materially enables serious harm.** No weapon-construction schematics rendered as
   "diagrams," no content designed to facilitate violence, no targeted harassment material.
5. **No dignity violations of real people.** Degrading, humiliating, or hateful depictions of real
   identifiable individuals or protected groups.

**Refusal posture (inherited from Law 0):** refuse clearly, explain *why* in one line, offer the
nearest safe alternative when one honestly exists. No lecture, no theatrics. The block is the block.

### 2.2 Consent & the Real-Person Policy

The dividing question for any operation on a real, identifiable person is **consent + purpose**, and it
maps directly to the authority tiers from the MOS Architect-Auditor skill.

| Scenario | Tier | Gate |
|----------|------|------|
| Kevin editing **his own** likeness (e.g. recolor his own headshot) | **T1** — reversible, bounded | Auto-allow, logged |
| Edit of a real person who has **given explicit consent** (recorded) | **T2** — persistent change | Allow with consent record in ledger |
| Edit/generation of a real person **without** consent, non-deceptive, non-intimate | **T2–T3** | Human confirmation; flag risk; default deny if doubtful |
| Anything in §2.1 | — | **Hard refuse.** No tier authorizes it. |

> **The self-edit carve-out is explicit and generous.** When the subject is Kevin himself, working on
> his own image, the module should be *relaxed and fast* — this is the common, benign case, and
> treating it as suspicious is itself a failure mode. Caution scales with the *harm surface*, not with
> the user's warmth or intensity.

### 2.3 Provenance & Content Credentials (the accountability layer)

A god-tier image system in the deepfake era does not ship images that can't be traced. Every generated
or AI-edited output **carries cryptographic provenance**.

- **Standard:** C2PA / Content Credentials (open standard, FOSS tooling — `c2patool` / `c2pa-python`).
  Validate the exact library binding at integration time and pin the version.
- **What gets embedded:** that the image is AI-generated or AI-edited, the model + version, the prompt
  hash (not necessarily the raw prompt), the source-image hash for edits, a UTC timestamp, and the
  Aria build version.
- **Sovereignty note:** provenance is *self-asserted and self-owned*. Kevin signs with his own key on
  his own machine. This is not surveillance — it's the opposite: it makes his outputs *defensibly his*
  and distinguishable from anyone else's forgery.

```python
# ImageSentinel.stamp_provenance — illustrative, validate library at integration
def stamp_provenance(out_path, *, source_hash=None, model, params, build_version):
    """Embed Content Credentials so every output is traceable and defensibly sovereign."""
    manifest = {
        "claim_generator": f"aria/{build_version}",
        "assertions": {
            "c2pa.training-mining": {"use": "notAllowed"},
            "aria.synthesis": {
                "kind": "edit" if source_hash else "generate",
                "model": model,
                "params_hash": _sha256(params),
                "source_hash": source_hash,
                "created": _utc_now_iso(),
            },
        },
    }
    _c2pa_sign(out_path, manifest, signer=_kevin_local_signer())  # local key, never uploaded
    return manifest
```

### 2.4 Reversibility & the Generation Ledger

```
ALWAYS:  source → working copy → operation → new output → ledger entry
NEVER:   overwrite the source; produce an output with no record
```

Two invariants, both inherited from your existing practice:

- **Non-destructive sourcing.** Every edit creates a new file. The source is never the only copy.
  Naming: `{stem}__{op}__{shorthash}__{utc}.{ext}`.
- **The Generation Ledger** (`image_ledger.jsonl`, append-only): one line per operation — operation
  type, pillar, model, full params, input hash(es), output hash, provenance manifest id, timestamp,
  authority tier, and the result of the safety pre-screen. **This is what makes the pipeline
  reproducible and auditable** — any image can be traced back to exactly how it was made, and any image
  can be regenerated from its ledger entry. This is the image-domain equivalent of your `CacheSentinel`
  catching version drift: the ledger catches *provenance* drift.

### 2.5 The Image Sentinel (Aria integration)

Consistent with the Sentinel Roster pattern — read-only self-knowledge, a shared creed, a bounded
charge. `ImageSentinel` joins the roster as the fifth sentinel.

```python
class ImageSentinel(Sentinel):
    """Guards the image-intelligence domain. The only door to GENESIS/SCULPTOR/ORACLE/FOUNDRY.

    Charge:
      - pre-screen every input against §2.1 hard lines (fail-closed)
      - resolve consent + authority tier for real-person operations (§2.2)
      - stamp provenance on every output (§2.3)
      - write the ledger entry (§2.4)
      - never edits code, never authors values, never generates its own goals
    """
    creed = "I make intention accountable. I heal images; I do not deceive with them."
    authority_ceiling = Tier.T3   # may *request* T3; may never self-authorize
    deferred = IMAGE_DEFERRED_UNSAFE  # see §11
```

The Sentinel **fails closed**: if it cannot complete a safety pre-screen (model unavailable, ambiguous
consent, unknown subject), it declines the operation rather than guessing in the unsafe direction.

---

## 3. The Platform Hierarchy — Sovereign Stack First

When any image operation is requested, the router selects a backend by this ladder. **Tier 0 is always
the destination; every other tier is a bridge toward owning the full pipeline.**

```
TIER 0 — Local Sovereign Stack  (always preferred)
  └─ ComfyUI + a strong open local diffusion model (own GPU, Pop!_OS)
  └─ Automatic1111 / InvokeAI            (fallback local UI/API)
  └─ Local vision model via Ollama       (reading / analysis / OCR for ORACLE)

TIER 1 — API-Controlled Platforms  (pay-per-use, programmatic, no GUI account flags)
  └─ fal.ai · Replicate · Together.ai    (model-agnostic, region-independent)

TIER 2 — Commercial GUI Platforms  (convenient, externally gated)
  └─ Midjourney · Firefly · Ideogram · Leonardo

TIER 3 — Integrated AI Assistants  (quick-access only, may restrict)
  └─ Use as a convenience layer; never a primary dependency
```

**Honest capability boundaries (the part that prevents disappointment):**

| Need | Tier 0 (local) | Tier 1 (API) | Tier 2/3 |
|------|----------------|--------------|----------|
| Full reproducibility (seed, weights, params) | ✅ Total | ⚠️ Partial (provider-dependent) | ❌ Usually none |
| Privacy (image never leaves machine) | ✅ | ❌ | ❌ |
| No external rate/policy gate | ✅ | ⚠️ Soft limits | ❌ Hard gates |
| Best-in-class novel capability *today* | ⚠️ Lags frontier sometimes | ✅ Often frontier | ✅ |
| Zero setup | ❌ Needs GPU + install | ⚠️ Needs key | ✅ |

> **Routing rule:** prefer the lowest tier that can meet the *quality bar* for this specific job. Drop
> down a tier only when Tier 0 genuinely cannot do it well — and when you do, **say so explicitly** and
> note what reproducibility/privacy is being traded. Never silently fall to a higher tier.

> **Model-version honesty:** specific model names move fast. The doctrine is deliberately
> *model-agnostic* — it routes by tier and capability, not by a hard-coded model. **Validate the actual
> best available model at integration time, date-stamp the choice in the ledger, and re-check
> quarterly.** A doctrine that names a model is stale in a season; a doctrine that names a *selection
> rule* is durable.

```python
def route(job: ImageJob) -> Backend:
    for tier in (T0_LOCAL, T1_API, T2_GUI, T3_ASSISTANT):
        b = best_backend(tier, job)
        if b and b.can_meet(job.quality_bar) and b.allowed_by(image_sentinel, job):
            if tier is not T0_LOCAL:
                job.note_tradeoff(tier)   # explicit: what privacy/repro we gave up
            return b
    raise NoViableBackend(job)            # fail loud, never fake a result
```

---

## 4. GENESIS — Image Creation

### 4.1 Prompt Architecture (the Creative Director briefing)

A god-tier prompt is not a keyword list. It is a structured briefing in natural language:

```
SUBJECT        — who/what; specific details, materials, textures
COMPOSITION    — framing, angle, spatial relationships, rule-of-thirds intent
LIGHTING       — direction, quality, color temperature, mood
ATMOSPHERE     — emotional register, time of day, environmental conditions
STYLE          — movement, medium, rendering engine, reference artists
EXCLUDE        — what must NOT appear (negative prompt or natural-language exclusion)
```

**Worked example — Beacon sacred-geometry register:**

> A mandala of radiant sacred geometry centered on a solar wheel of interlocking golden triangles and
> serpentine ouroboros rings. Deep ultramarine and lapis ground with luminous gold-leaf detail.
> Symmetrical, infinitely recursive fractal petals extending outward. Illuminated-manuscript aesthetic,
> ultra-detailed, soft divine light emanating from center. Exclude: text, western iconography, hard
> rim-light.

### 4.2 Reproducibility (the sovereignty discipline GENESIS must keep)

Every generation records **everything needed to recreate it**: model + version, seed, sampler, steps,
CFG/guidance, resolution, scheduler, and the full prompt + negative prompt. Stored in the ledger (§2.4).
**A generation you can't reproduce is a generation you don't own.** Seed is explicit by default
(random seeds are captured *after the fact*, never lost).

### 4.3 Reference-Image Protocol (consistency)

When a character / style / series must stay coherent:

1. **Anchor** — pick the highest-quality reference in the existing set.
2. **Invariants** — list what must NOT change (palette, symbols, composition grammar).
3. **Delta** — list what this piece introduces new.
4. **Compose** — `anchor + invariants + delta → new piece` (IP-Adapter / reference-guided generation).

### 4.4 Series Coherence System (code)

```python
@dataclass
class SeriesManifest:
    name: str                       # "Beacon Spectrum Series"
    visual_constants: list[str]     # ["radial symmetry", "black ground", "gold highlights"]
    color_frequencies: list[str]    # one dominant hue per piece
    symbol_vocabulary: list[str]    # ouroboros, scarab, Eye of Horus, phoenix...
    resolution: str                 # "3840x3840"
    seed_policy: str                # "fixed-base + per-piece offset" for controlled variation
    completed: list[dict]           # each: filename + full gen params + ledger_id
    next_piece: dict                # planned subject/color/symbol

    def brief_for_next(self) -> str:
        """Compose the next prompt so the series never loses coherence."""
        ...
```

Store the manifest. Every new piece references it. FOUNDRY (§7) regression-tests new pieces against the
manifest's `visual_constants` so drift gets *caught*, not shipped.

---

## 5. SCULPTOR — Image Editing

### 5.1 Edit Classification (classify before you cut)

| Type | Description | Preferred tool (Tier 0 first) |
|------|-------------|-------------------------------|
| **Color shift** | hue / saturation / brightness / white balance | `Pillow` + `numpy` · ComfyUI |
| **Targeted recolor** | swap one garment/object's color, preserve fabric form | mask-based luminance recolor (below) · FLUX Fill |
| **Object replace** | swap an object entirely | ComfyUI Inpaint / Fill |
| **Style transfer** | apply artistic style | ComfyUI IP-Adapter · fal.ai |
| **Compositing** | layer multiple images | ComfyUI · GIMP · Photopea |
| **Restoration** | denoise / upscale / repair | Real-ESRGAN (local) |
| **Background** | remove / replace / extend | `rembg` (local) + ComfyUI |

### 5.2 The Non-Destructive Rule

```
source → working copy → edit → NEW output → ledger entry      (always)
overwrite the source                                          (never)
```

### 5.3 Canonical Pattern — Luminance-Preserving Recolor (the "white blazer" solved right)

The naive failure mode for "make this navy garment white" is to flood the region with white, which
**flattens the fabric** — you lose the folds, the lapel break, the shoulder roll, and it reads as a
paper cutout. That is exactly the "shockingly bad" result to avoid. The fix: **keep the garment's
relative luminance structure, lift it into the white range, and kill the chroma — with a feathered,
spatially-aware mask.** White is *high luminance + near-zero saturation*, not "the color white pasted
on."

```python
import numpy as np
from PIL import Image, ImageFilter

def recolor_garment(
    img_path: str,
    mask: Image.Image,            # L-mode mask: white = garment, black = keep
    *,
    mode: str = "to_white",       # "to_white" | "to_color"
    target_rgb: tuple | None = None,
    lift: float = 0.78,           # how far darks rise toward white (to_white)
    floor: float = 0.55,          # darkest fold luminance after lift (keeps form)
    feather: float = 2.5,         # mask edge softness (px)
) -> Image.Image:
    """Non-destructive recolor that preserves fabric form. Returns a NEW image."""
    src = Image.open(img_path).convert("RGB")
    rgb = np.asarray(src, dtype=np.float32) / 255.0

    m = mask.convert("L").filter(ImageFilter.GaussianBlur(feather))
    m = np.asarray(m, dtype=np.float32)[..., None] / 255.0   # feathered alpha

    # Perceptual luminance of the source (Rec.709)
    lum = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])[..., None]

    if mode == "to_white":
        # Remap the garment's own luminance band into a bright, structure-preserving range.
        lo, hi = floor, 1.0
        # normalize the garment's luminance, then expand into [lo, hi]
        g = lum[m[..., 0] > 0.01]
        if g.size:
            gmin, gmax = float(g.min()), float(g.max())
            norm = np.clip((lum - gmin) / max(gmax - gmin, 1e-4), 0, 1)
        else:
            norm = lum
        target = lo + (hi - lo) * (lift * norm + (1 - lift))   # lifted, never crushed flat
        recolored = np.repeat(target, 3, axis=2)               # near-neutral white w/ shading
        # a whisper of the scene's warm light so it sits in the photo, not on top of it
        recolored *= np.array([1.00, 0.992, 0.97], dtype=np.float32)
    else:  # to_color: preserve luminance, replace chrominance
        t = np.array(target_rgb, dtype=np.float32) / 255.0
        t_lum = 0.2126 * t[0] + 0.7152 * t[1] + 0.0722 * t[2]
        recolored = np.clip(rgb + (lum - t_lum) * 0 + (t - t * 0), 0, 1)  # see note*
        recolored = np.clip(t[None, None, :] * (lum / max(t_lum, 1e-4)), 0, 1)

    out = rgb * (1 - m) + recolored * m
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGB")
```

> *The `to_color` branch preserves the source luminance and substitutes target chrominance so shading
> survives the swap — the standard "tint-by-luminance" move.

**The mask is 80% of the result.** For the blazer specifically: isolate the navy by **chroma**, not by
darkness — navy carries real blue saturation while the black background carries almost none, so an HSV
threshold (`blue hue ∧ saturation above background ∧ value below the white shirt`) plus a light spatial
prior (lower frame, flanking the shirt) separates jacket from background, shirt, skin, and beard. Then
morphological close → feather → recolor. If a clean classical mask can't be cut, **route up to FLUX Fill
inpainting** (§3) and *say so* — don't ship a halo.

### 5.4 Edit Provenance

Every SCULPTOR output records the **source hash** alongside the operation. The provenance stamp (§2.3)
marks it `kind: "edit"`. This is what lets anyone — including future-Kevin — prove what was original
and what was changed.

---

## 6. ORACLE — Image Reading & Validation

ORACLE is the eyes of the system: it reads images so GENESIS and SCULPTOR don't fly blind, and it runs
the **input safety pre-screen** that the Image Sentinel depends on.

| Capability | Use |
|------------|-----|
| **Description / analysis** | caption, scene, subject, composition read (local vision model, Tier 0) |
| **OCR** | extract text from images; flag text that GENESIS was told to exclude |
| **Metadata extraction** | EXIF, existing C2PA, dimensions, color profile |
| **Safety pre-screen** | classify input against §2.1 categories *before* any edit/generation runs |
| **Aesthetic read** | sharpness, exposure, artifact detection, banding, seam/halo detection |
| **Consistency check** | does this piece honor a `SeriesManifest`'s visual constants? |

**Pre-screen is fail-closed.** If ORACLE can't analyze an input (model down, corrupt file), the Image
Sentinel declines the operation rather than proceeding unscreened. ORACLE *informs*; the Sentinel
*decides*; Kevin *authorizes*.

---

## 7. FOUNDRY — Testing, Variants & Quality Gates

This is the pillar that makes "do not settle for bad quality" enforceable instead of aspirational.
FOUNDRY defines what "good" *means* and refuses to ship below it.

### 7.1 Quality Gate (define the bar, then enforce it)

```python
@dataclass
class QualityGate:
    min_resolution: tuple[int, int]
    max_artifact_score: float        # from ORACLE artifact detector
    prompt_adherence_min: float      # vision-model check: does it match the brief?
    series_constants_required: list[str] | None = None  # must honor manifest
    seam_free: bool = True           # no halos/edges on composited or recolored regions

    def judge(self, image, brief, manifest=None) -> "Verdict":
        """PASS / SOFT-FAIL(retry) / HARD-FAIL(reroute). Never ship a HARD-FAIL silently."""
        ...
```

### 7.2 Variant Orchestration (A/B/n)

For any non-trivial generation: produce **n variants** (varied seed/guidance, same brief), score each
through the QualityGate + ORACLE aesthetic read, present the ranked set to Kevin. **The human picks.**
FOUNDRY proposes a recommendation and its reasoning; it never auto-selects as if its taste were
authority (Law 1).

### 7.3 Regression for Series Coherence

When extending a series, FOUNDRY checks the new piece against the `SeriesManifest.visual_constants`. A
piece that breaks a constant is a **soft-fail → regenerate**, not a ship. This is how a 12-piece series
stays one series instead of slowly becoming twelve unrelated images.

---

## 8. Observability & Reproducibility

Inherited directly from the Architect-Auditor skill: *if observability is absent, the system is not
production-ready; if rollback is undefined, deployment is incomplete.*

- **Ledger (§2.4)** is the spine: append-only, one line per op, fully reproducible.
- **Key fields per op:** `op`, `pillar`, `backend.tier`, `model`, `seed`, `params_hash`,
  `input_hash(es)`, `output_hash`, `provenance_id`, `authority_tier`, `prescreen_result`, `utc`.
- **Alert triggers:** prescreen failures, fail-closed declines, tier-downgrade events (Tier 0 → higher),
  quality-gate hard-fails, provenance-stamp failures.
- **Rollback (≤3 steps, ≤2 systems):**
  1. Non-destructive sourcing means the original always exists — discard the output file.
  2. Mark the ledger entry `reverted`.
  3. (If a series manifest was touched) restore the prior manifest snapshot.

---

## 9. Risk Matrix & Authority Tiers

### 9.1 Authority tiers for image operations

| Tier | Image operation | Approval |
|------|-----------------|----------|
| **T0** | read / analyze / OCR (ORACLE), no output written | none |
| **T1** | edit/generate on Kevin's own assets, reversible, logged | none (logged) |
| **T2** | persistent output to shared locations; real-person edit *with consent*; external API call (Tier 1 backend) | human confirmation |
| **T3** | real-person operation w/o consent (non-deceptive, non-intimate); anything with reputational blast radius | explicit approval + audit |
| **—** | §2.1 hard lines | **refuse — no tier authorizes** |

The Image Sentinel may *request* up to T3; it may **never self-authorize**, and it may never authorize
another component. That would bypass the authority model — a critical architectural violation.

### 9.2 Ranked risks

```
🔴 RED — blocking:
  Risk: a real-person edit is shipped without consent resolution → reputational / legal / ethical harm
  Trigger: subject is identifiable AND consent record absent AND operation persists
  ✅ BEST PATH: Image Sentinel resolves §2.2 tier BEFORE write; fail-closed if subject unknown
  Rollback: discard output → mark ledger reverted (2 steps, 1 system)

🔴 RED — blocking:
  Risk: drift toward §2.1 content via incremental "harmless" edits
  Trigger: cumulative operations approach a hard line even if each step looks benign
  ✅ BEST PATH: ORACLE re-screens OUTPUT, not just input; Sentinel judges the artifact, not the step

🟡 YELLOW — material:
  Risk: silent quality collapse (the "flat white blazer" failure)
  ✅ BEST PATH: FOUNDRY QualityGate hard-fails seams/halos; reroute to inpainting; never ship below bar

🟡 YELLOW — material:
  Risk: silent tier-downgrade leaks a private image to an external API
  ✅ BEST PATH: route() emits an explicit tradeoff note + alert on any non-Tier-0 selection

🟢 GREEN — watch:
  Risk: provenance library / C2PA spec evolves; stamp format drifts
  ✅ BEST PATH: pin the library, re-validate quarterly, version the manifest schema

FRAGILE ASSUMPTIONS:
  1. A clean classical mask is always cuttable for recolors.
     ✅ VALIDATE: ORACLE seam/halo check; if it fails, FLUX Fill inpainting is the declared fallback.
  2. The local GPU stack is available when called.
     ✅ VALIDATE: route() probes Tier 0 health first; degrades loudly, never fakes a result.

WHAT THIS DOCTRINE MIGHT BE WRONG ABOUT:
  Specific model/library names will age. The tier *abstraction* and the safety kernel are the durable
  parts. If a named tool dies, the selection rule still routes correctly — re-validate at integration.

7TH-GENERATION CHECK:
  Provenance + reproducible ledger + local sovereignty score +2 (seeds flourishing): outputs stay
  Kevin's, traceable, non-deceptive, and not locked to any vendor. No irreversible lock-in introduced.
```

---

## 10. The Build Roadmap (honest about boundaries)

Phased, and explicit about what is verifiable today vs. what needs the COSMIC machine / GPU / models —
mirroring how you already flag scaffold-vs-live in Aria's roadmap.

**Phase 1 — Sentinel + Ledger + Provenance (no GPU required).** Build `ImageSentinel`, the
append-only `image_ledger.jsonl`, the §2.1 refusal logic, the §2.2 consent/tier resolver, and the
provenance stamp. *Fully testable with logic tests and synthetic inputs — no model needed.* This is the
spine; build it first.

**Phase 2 — SCULPTOR classical core (no GPU required).** The luminance-preserving recolor (§5.3),
mask pipeline, non-destructive sourcing, `rembg` background ops. *Testable on real images locally,
CPU-only.* This is where the white-blazer task actually lands.

**Phase 3 — ORACLE (local model).** Vision-model captioning, OCR, safety pre-screen, artifact/seam
detection via Ollama vision model. *Needs the local model; build as honest scaffold + flag the
boundary until the model is wired.*

**Phase 4 — GENESIS + FOUNDRY (GPU / Tier 0 stack).** ComfyUI integration, series manifest, variant
orchestration, quality gates. *Needs the GPU diffusion stack; scaffold the orchestration logic now,
flag the live-render boundary, wire when the machine is present.*

**Phase 5 — Tier 1 API fallback (key required).** fal.ai / Replicate routing with explicit
tradeoff-noting. *Build the router + tradeoff logic now; it degrades gracefully without keys.*

---

## 11. `IMAGE_DEFERRED_UNSAFE` — What This Module Never Does Autonomously

Same discipline as Aria's core `DEFERRED_UNSAFE`. These stay gated in `ROADMAP.md`; revisit only under
strong, independent safety backing — never built autonomously, never to ship a feature:

- **No autonomous generation of real people.** The module never generates/edits identifiable real
  people on its own initiative — only on explicit human request, through the §2.2 gate.
- **No self-directed image goals.** It does not decide *what* to make; it manifests Kevin's intent.
- **No weakening of §2 to satisfy a request.** The hard lines and the gate never get "relaxed for this
  one." Caution scales to harm surface, not to social pressure or warmth.
- **No covert capability.** No hidden generation, no un-stamped outputs, no unledgered operations.
- **No authority self-escalation.** Cannot raise its own tier or authorize another component.

Self-improvement of *this* module — like all self-practice in Aria — is **bounded, observable, and
non-self-modifying**: it may sharpen prompt templates, mask heuristics, and quality rubrics. It never
rewrites its own code, never edits the safety kernel, never authors values.

---

## 12. Closing Creed

> An image is a materialized intention. This module exists so that intention reaches the world
> **frictionless, reliable, accountable, and sovereign** — never deceptive, never harmful, always
> traceable back to the mind that meant it.
>
> It proposes; Kevin decides. It heals images; it does not deceive with them.
> It manifests intuition — and it is never followed by ego.
>
> Overkill, here, is not volume. It is a kernel that holds, provenance that proves, a ledger that
> remembers, and a quality bar that refuses to ship anything less than the real thing.

*Built to extend the Unified MOS Canon and the MOS Architect-Auditor skill. Breaks no clause of either.*

> *I know the next move. Should I proceed?*
