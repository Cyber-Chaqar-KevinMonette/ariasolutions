# aria-quality-tribunal — advocates and audits, made standing (Quality round · Q3)

> Kevin: *"Or quality advocates and audits."* Almost entirely composition
> + one real, verified bug fix — the Tribunal and Advocate Spectrum were
> already rich; they were just never STANDING, and one of them was
> dormant.

## A real bug, fixed
`tribunal.log_to_diagnosis()` had **never successfully run**: it opened a
conflict with `type="tribunal-review"`, which isn't a member of
`diagnosis.CONFLICT_TYPES`. `open_conflict()` raised `CatalogError` every
time, silently swallowed by a blanket `except Exception: return None`.
Zero callers existed anywhere in `src/` or `tests/`. Fixed to use the real
`"ambiguity"` type (a tribunal convenes precisely when something is
uncertain enough to need review) plus the existing, previously-unused
`prefix` parameter, keeping the "tribunal-review" identity in the case-ID
namespace (`TRIB-001`) instead of the invalid `type` field.

## Real measured data over prose heuristics
`spectrum/lenses.py`'s `artisan()` lens scored craft/cleanliness from
prose pattern-matching only (`test`, `todo`, `hack`, …). When the
proposal now carries real measured data (`quality_score` /
`hardening_critical_ok`, from Q1's ledger), that overrides the heuristic
— measured beats pattern-matched. Absent those keys, byte-identical
fallback; every existing bare-string or plain-dict caller is unaffected.

## Standing, not one-shot
`QualitySentinel`'s marked extension seam (left there deliberately in Q1)
gets a second scan phase: convene **both** Tribunal and Advocate Spectrum
over the same real recent work Q1 just scored, logged through the
now-fixed `log_to_diagnosis()` into the same `diagnosis.ConflictCatalog`
Tribunal already uses. The standing counterpart to `TribunalSentinel`,
which only re-checks a hardcoded safety string — this one audits real
work. Best-effort: a scrutiny failure here never breaks the quality scan.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-quality-tribunal
./scripts/safe_apply.sh aria-quality-tribunal
```
