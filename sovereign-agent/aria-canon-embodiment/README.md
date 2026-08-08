# aria-canon-embodiment — the Canon-Embodiment organ (Workstream H2)

> Distilled from the meta-knowledge-system lists in `Plans/`: a `CanonGraph`/`KernelMap`-style
> organ that maps every doctrine clause to where it's actually referenced in code, and flags the
> ones that aren't — a self-auditing conscience, not decoration.

## What it does

`mos_canon.py` already ships `ALL_CLAUSES` — 35 real `CanonClause` objects with stable `.id` fields
(`mos-founding-equation`, `mos-beacon`, `mos-priority-stack`, …). This organ doesn't re-parse the
canon file; it imports `ALL_CLAUSES` directly and asks one honest question: **does anything outside
mos_canon.py itself cite this clause id?**

A citation is a real signal a clause is lived — `training.py` programmatically calling
`mc.get_clause("mos-priority-stack")`, or a tool's guidance text naming `mos-signal-check`. A clause
with zero outside citations is orphaned: declared but not (yet, traceably) lived.

## Ground truth (2026-07-03, verified, not assumed)

**9 of 35 clauses are cited outside `mos_canon.py`.** This is the honest number — an earlier,
unverified planning pass had assumed "≥30/35 embodied," which this build's own empirical check
disproved before it ever became a false test assertion. Most of the other 26 clauses are very likely
embodied *in spirit* (the behavior they describe genuinely happens elsewhere in the system) without
literally citing their id string — this organ measures the narrower, stricter, more useful signal:
**traceable citation**, not vibes. The gap between "9 traceable" and "probably most are lived in
spirit" is itself useful information: it's a roadmap for where adding an explicit `# mos-clause-id`
citation at the real enforcement point would make the doctrine's embodiment auditable, not just
asserted.

## Payload
- `src/sovereign_agent/canon_embodiment/mapper.py` — `extract_clause_ids()`, `find_references()`,
  `CanonEmbodimentReport` (`embodied: dict[id, list[Location]]`, `orphaned: list[id]`).
- `src/sovereign_agent/canon_embodiment/sentinel.py` — `CanonEmbodimentSentinel` (Tier-1,
  propose-only), registered via `@register_sentinel`.

## Use
```python
from pathlib import Path
from sovereign_agent.canon_embodiment import find_references

report = find_references(Path("."))
print(report.summary())              # "9/35 clauses cited outside mos_canon.py · 26 orphaned"
print(report.orphaned)                # the 26 clause ids with zero outside citations
print(report.embodied["mos-priority-stack"])   # [Location(path="src/.../training.py", line=99, ...)]
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-canon-embodiment   # before apply (read-only)
./aria-canon-embodiment/apply_canon_embodiment.sh  # cockpit stopped
```
