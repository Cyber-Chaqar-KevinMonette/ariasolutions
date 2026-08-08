# aria-godtier-scanner — Her Vision: Hold the Whole System to the God-Tier Canon

> The meta-scanner that scores every system, module, layer, and doc against `GOD_TIER_CANON.md`, surfaces
> every weak / fragile / neglected / sub-god-tier target transparently, and drafts propose-only
> enhancements. **Total coverage — nothing is neglected.** She reports everything before her.

## What it gives Aria

`godtier/` — her inner eye:
- `targets.py` — enumerate every target (staged modules, core src layers incl. the non-classical layer,
  docs). Total coverage; anything unscanned is itself a gap.
- `rubric.py` — score each against the canon rubric (`scripts/lib/god_tier_canon.json`): tests, docs,
  reversibility, cleanliness (no debug), robustness (error handling), non-classical parity. → 0..1 + band.
- `scanner.py` — rank weakest-first; report bands, average, god-tier fraction, coverage.
- `enhance.py` — for a gap, **draft** (never apply) a god-tier enhancement: remediation steps + scaffold
  command + the Tribunal/foresight gate to run first.

Sentinel `godtier_sentinel.py` (standing self-scan) + tools `godtier_scan`(T0), `godtier_gaps`(T0),
`godtier_draft_fix`(T1).

## Verified (honest, reproducible)

- Scans the real system: **126 targets · avg 0.78 · 64% god-tier** (bands: 81 god-tier · 15 strong · 25
  fragile · 1 weak · 4 neglected). The 4 neglected (e.g. `aria-docker-launch`, `aria-systems-audit`) are
  named transparently with their gaps + drafted fixes.
- The non-classical layer gets a **parity penalty** if untested (it must be god-tier on par with classical).
- Propose-only: drafts include the `pre_apply_gate` (Tribunal + 14-gen foresight) to run before any apply.
- 8 tests green.

The full living backlog is `GODTIER_GAP_REPORT.md`. Staged + reversible (backups at
`aria-godtier-scanner/backups/`); nothing in live `src/` changes until `apply_godtier.sh` runs. 💛
