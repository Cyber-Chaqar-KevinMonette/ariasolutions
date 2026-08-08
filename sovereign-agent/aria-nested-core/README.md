# aria-nested-core — Workstream E

Nest the Holographic BitNet's conditioning lever inside the Superposition
Processor's amplitude amplification — "one quantum core, BitNet/HRR as
inner organs," per the plan's own framing.

## A correction found while researching this workstream

The plan's own text described `nonclassical_supreme/` and
`aria_lm/holo_bitnet.py` as *"all proven, all staged, none applied yet."*
That was stale — both are already live in `src/` (no git diff, imports
cleanly, already committed). This is the same class of staleness the
session already found and corrected once for H1-H4/J/D/C. What genuinely
did **not** exist yet (confirmed via a repo-wide grep: zero references to
`HolographicConditioner` outside `aria_lm/` itself) is the actual
**nesting** the plan asks for. That's the real, narrower scope this module
closes.

## What this ships

`src/sovereign_agent/nonclassical_supreme/superpose.py` — 2 anchored
patches, no new file:

- `evolve()` gets two new **optional** kwargs: `holo_weight: float = 0.0`
  (an **exact no-op by default** — every existing caller's behavior is
  byte-for-byte unchanged, proven by a dedicated test) and
  `conditioner=None`. Only when a caller explicitly passes
  `holo_weight > 0` does a holographic bias blend into the alignment
  signal.
- `holographic_bias(state, query, *, conditioner=None)` — the actual
  nesting mechanism. Conditions `HolographicConditioner`'s HRR memory on
  the query's own Bloch phase, binds it against each candidate's phase,
  and returns a per-candidate bias in `[0, 1]`. **Lazily imports torch +
  holo_bitnet INSIDE the function**, never at module level — importing
  torch unconditionally would undermine `nonclassical_supreme`'s entire
  stated purpose (CPU-only, no GPU, no VRAM, tens of microseconds).
  Returns `None` (never raises) if torch/holo_bitnet aren't importable,
  so `evolve()` always has a pure-Python fallback.
- `evaluate_holographic_nesting(cases, *, holo_weight=0.3)` — the honest
  EXPAI evidence gate. Mirrors `fusion.py::PEIGConditioner`'s *pattern*
  ("starts as an exact no-op, only moves if evidence shows it helps") —
  **not** its literal `ab_compare()` call, which trains a full neural LM
  over 400+ iterations; `evolve()` has no trainable parameters and no
  gradient descent, so a training-loop A/B doesn't apply here. Instead,
  runs the same labeled `(query, candidates, expected)` cases through the
  baseline and nested paths and reports whether accuracy/confidence
  genuinely improves. `nesting_helps` is only `True` on a real margin —
  no claim without proof.

## Why it's safe by construction

- `holo_weight=0.0` is the default everywhere — a dedicated test proves
  `evolve(state, query)` and `evolve(state, query, holo_weight=0.0)`
  produce byte-identical results.
- No GPU/VRAM ceremony needed: `holo_bitnet.py` has zero `.cuda()` calls
  anywhere — this nesting stays CPU-only naturally, which is the whole
  point of the module it's nesting into.
- Nothing here is self-modifying or auto-tuning. A caller must explicitly
  set `holo_weight > 0` after reviewing `evaluate_holographic_nesting()`'s
  evidence — bounded, observable, per doctrine.

## Tests

`tests/test_patcher.py` (10 tests) — the patch applies cleanly against
the CURRENT live file, is idempotent, compiles, `evolve()`'s new kwargs
default correctly, the bias only blends when `holo_weight > 0`, torch is
confirmed imported lazily (not at module level), a missing anchor raises
`PatchError`.

`tests/test_nested_core.py` (7 tests, staging only, shadow-copy) /
`tests/test_nested_core_live.py` (same 7, promoted to live `tests/` after
apply, plain imports, zero `sys.modules` manipulation): `holo_weight=0.0`
is byte-identical to the pre-existing default; `holographic_bias` returns
a bias per candidate in `[0, 1]`; a positive `holo_weight` genuinely
changes the result distribution (proves the nesting is wired in, not
silently ignored); `holographic_bias` never raises on empty candidates;
`evaluate_holographic_nesting` reports honest deltas and never claims
help on a zero delta; the pre-existing `process()` convenience function
still works completely unmodified.

Reversible: restore `superpose.py` from the backup.
