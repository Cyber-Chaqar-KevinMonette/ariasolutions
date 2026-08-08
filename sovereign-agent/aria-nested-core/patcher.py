"""patcher.py — Workstream E: nest the Holographic BitNet's conditioning
lever inside the Superposition Processor's amplitude amplification.

**A correction found while researching this workstream, not a build
surprise**: the plan's own text described `nonclassical_supreme/` and
`aria_lm/holo_bitnet.py` as "all proven, all staged, none applied yet" —
that was stale. Both are already live in `src/` (confirmed: no git diff,
imports cleanly, committed history) — the same class of staleness this
session already found and corrected once for H1-H4/J/D/C. What genuinely
does NOT exist yet (confirmed via grep: zero references to
`HolographicConditioner` outside `aria_lm/` itself) is the actual NESTING
the plan asks for: `HolographicConditioner.condition(context, phases)`
biasing `superpose.evolve()`'s amplitude amplification. That's the real,
narrower scope this patcher closes.

Design, mirroring `fusion.py::PEIGConditioner`'s "starts as an exact
no-op, only moves if evidence shows it helps" idiom — NOT its literal
`ab_compare()` call (that trains a full neural LM over 400+ iterations;
`evolve()` has no trainable parameters and no gradient descent, so a
full training-loop A/B doesn't apply here):

- `holographic_bias()` — a NEW function computing a per-candidate bias
  signal from `HolographicConditioner.condition()`. Lazily imports torch
  + holo_bitnet INSIDE the function, never at module level — importing
  torch unconditionally would undermine `nonclassical_supreme`'s entire
  stated purpose (CPU-only, torch-free, "no GPU, no VRAM"). Returns
  `None` (never raises) if torch/holo_bitnet aren't importable.
- `evolve()` gets two new, OPTIONAL keyword args: `holo_weight: float = 0.0`
  (exact no-op by default — every existing caller's behavior is
  byte-for-byte unchanged) and `conditioner=None`. Only when a caller
  explicitly passes `holo_weight > 0` does the holographic bias blend
  into the alignment signal.
- `evaluate_holographic_nesting()` — the honest EXPAI evidence gate: runs
  the SAME labeled (query, candidates, expected) test cases through both
  the baseline (`holo_weight=0.0`) and nested (`holo_weight>0`) paths and
  reports whether accuracy/confidence genuinely improves.
  `nesting_helps` is only True if the nested version wins by a real
  margin — no claim without proof, per doctrine.

Anchored span patches against the CURRENT live superpose.py (same
discipline as every other patcher this session — not a full-file
replace).
"""
from __future__ import annotations

MARK = "nested-core-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. evolve() gets two new optional kwargs + the blend branch ────────────

EVOLVE_ANCHOR = (
    'def evolve(state: SuperpositionState, query: str, *, iterations: int = 2, sharpness: float = 2.0) -> SuperpositionState:\n'
    '    """Amplitude-amplify candidates whose phase aligns with the query (interference). Grover-like.\n'
    '\n'
    '    Each iteration multiplies amplitude by a non-negative factor growing with phase alignment\n'
    '    cos(φ_cand − φ_query), so aligned candidates grow (constructive) and misaligned shrink (destructive).\n'
    '    """\n'
    '    if not state.candidates:\n'
    '        return state\n'
    '    # The amplification signal is genuine query↔candidate similarity, carried as phase alignment:\n'
    '    # similar candidates sit near the query phase (constructive interference), dissimilar ones near\n'
    '    # anti-phase (destructive). This is honest amplitude amplification toward the best answer.\n'
    '    sims = [similarity(query, str(c)) for c in state.candidates]\n'
    '    for _ in range(max(1, iterations)):\n'
)
EVOLVE_NEW = f'''def evolve(state: SuperpositionState, query: str, *, iterations: int = 2, sharpness: float = 2.0,
           holo_weight: float = 0.0, conditioner=None) -> SuperpositionState:
    """Amplitude-amplify candidates whose phase aligns with the query (interference). Grover-like.

    Each iteration multiplies amplitude by a non-negative factor growing with phase alignment
    cos(φ_cand − φ_query), so aligned candidates grow (constructive) and misaligned shrink (destructive).

    {MARK} — holo_weight (default 0.0, an EXACT no-op — every existing caller's
    behavior is byte-for-byte unchanged): when > 0, blends a nested holographic-
    binding bias (see holographic_bias() below, which conditions the HolographicBitNet's
    HRR memory on this state's own Bloch phases) into the alignment signal. Off by
    default per the EXPAI doctrine — see evaluate_holographic_nesting() for the honest
    evidence gate that must show real improvement before this is ever turned on for a
    real caller. `conditioner` lets a caller reuse one HolographicConditioner instance
    across calls instead of constructing a fresh one each time (cheaper, deterministic).
    """
    if not state.candidates:
        return state
    # The amplification signal is genuine query↔candidate similarity, carried as phase alignment:
    # similar candidates sit near the query phase (constructive interference), dissimilar ones near
    # anti-phase (destructive). This is honest amplitude amplification toward the best answer.
    sims = [similarity(query, str(c)) for c in state.candidates]
    if holo_weight > 0.0:  # {MARK}
        bias = holographic_bias(state, query, conditioner=conditioner)
        if bias is not None:
            sims = [(1.0 - holo_weight) * s + holo_weight * b for s, b in zip(sims, bias)]
    for _ in range(max(1, iterations)):
'''


# ── 2. new holographic_bias() + evaluate_holographic_nesting(), after entangle() ──

ENTANGLE_END_ANCHOR = (
    '    except Exception:  # noqa: BLE001 — physics import optional; degrade to amplitude correlation\n'
    '        return 0.0\n'
)
NESTED_CORE_FUNCTIONS = f'''

# ── {MARK} — Workstream E: nest the Holographic BitNet inside the processor ──

def holographic_bias(state: SuperpositionState, query: str, *, conditioner=None) -> list[float] | None:
    """A per-candidate bias signal from HolographicConditioner's binding of the
    query's own Bloch phase with each candidate's phase — the nested non-classical
    (PEIG-adjacent) + HRR conditioning lever from aria_lm/holo_bitnet.py, applied to
    THIS processor's own candidates rather than a neural LM's token embeddings.

    Lazily imports torch + holo_bitnet — never at module level. Importing torch
    unconditionally here would undermine nonclassical_supreme's entire stated
    purpose (CPU-only, no GPU, no VRAM, tens of microseconds). Returns None (never
    raises) if torch/holo_bitnet aren't importable, so evolve() can always fall
    back to the pure-Python baseline.
    """
    try:
        import torch

        from sovereign_agent.aria_lm.holo_bitnet import HolographicConditioner
    except Exception:  # noqa: BLE001 — torch/holo_bitnet optional
        return None

    if conditioner is None:
        conditioner = HolographicConditioner(dim=16)
    dim = conditioner.dim

    query_phase = _phase_of(query)
    context = torch.zeros(dim)
    context[0] = math.cos(query_phase)
    context[1] = math.sin(query_phase)
    bound = conditioner.condition(context, state.phases)

    biases: list[float] = []
    for ph in state.phases:
        cand_vec = torch.zeros(dim)
        cand_vec[0] = math.cos(ph)
        cand_vec[1] = math.sin(ph)
        sim = torch.nn.functional.cosine_similarity(
            bound.unsqueeze(0), cand_vec.unsqueeze(0)
        ).item()
        biases.append(max(0.0, sim))  # clamp negative similarity — never penalize below the floor
    return biases


def evaluate_holographic_nesting(cases: list[dict], *, holo_weight: float = 0.3,
                                  iterations: int = 2) -> dict:
    """The honest EXPAI evidence gate (mirrors fusion.py::ab_compare's PATTERN —
    "no claim without proof" — applied to this lightweight processor instead of a
    full neural training run, since evolve() has no trainable parameters).

    `cases` is a list of {{"query": str, "candidates": list, "expected": <one of
    candidates>}}. Runs the SAME cases through the baseline (holo_weight=0.0) and
    nested (holo_weight=holo_weight) paths and reports whether accuracy/confidence
    genuinely improves. `nesting_helps` is only True if the nested version wins by
    a real margin, never on a coin-flip difference.
    """
    def _run(weight: float) -> dict:
        correct = 0
        conf_total = 0.0
        for case in cases:
            state = prepare(list(case["candidates"]))
            evolve(state, case["query"], iterations=iterations, holo_weight=weight)
            result = measure(state, seed=0)
            if result["result"] == case["expected"]:
                correct += 1
            conf_total += result["confidence"]
        n = len(cases) or 1
        return {{"accuracy": correct / n, "avg_confidence": conf_total / n}}

    baseline = _run(0.0)
    nested = _run(holo_weight)
    acc_delta = round(nested["accuracy"] - baseline["accuracy"], 4)
    conf_delta = round(nested["avg_confidence"] - baseline["avg_confidence"], 4)
    return {{
        "baseline": baseline,
        "nested": nested,
        "accuracy_delta": acc_delta,
        "confidence_delta": conf_delta,
        "nesting_helps": acc_delta > 0.02 or (acc_delta == 0.0 and conf_delta > 0.02),
    }}
'''


def patch_superpose(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, EVOLVE_ANCHOR, EVOLVE_NEW, label="evolve anchor")
    text = _replace_once(
        text, ENTANGLE_END_ANCHOR, ENTANGLE_END_ANCHOR + NESTED_CORE_FUNCTIONS,
        label="entangle end anchor",
    )
    return text, True
