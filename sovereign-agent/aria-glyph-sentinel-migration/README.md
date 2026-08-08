# aria-glyph-sentinel-migration

Migrates `stewardship/glyph_sentinel.py` to the unified `@register_sentinel`
pattern, so glyph health becomes visible in `sov sentinels list` /
`gather_health()` / `scan_all()` — previously invisible to that loop entirely.

## The gap

`glyph_sentinel.py` is a **functional module**: free functions
(`scan_source_tree`, `generate_proposals`, `detect_coverage_gaps`,
`load_catalog`/`save_catalog`) over plain dataclasses (`GlyphCatalog`,
`ReplacementProposal`, `CoverageGap`). It predates the unified `Sentinel`
ABC contract entirely — it never defines a `Sentinel` subclass, so it's
invisible to every registry-based discovery mechanism (`sov sentinels
list`, `gather_health()`, `scan_all()`, the Universal Scanner Kernel's
fan-out). It's real, live, used code (imported directly by `doctor.py`,
`cli.py`, `workflow/catalog.py`, `cosmic_fitness.py`) — just architecturally
inconsistent with every other sentinel in the codebase.

## The fix

A new `GlyphSentinel(Sentinel)` class **inside** `glyph_sentinel.py` that
*delegates* to the existing free functions unchanged:

- `scan()` — the expensive, explicit, on-demand full source-tree walk.
  Calls `scan_source_tree()` + `generate_proposals()` + `detect_coverage_gaps()`
  exactly as `doctor.py`'s own `check_glyph_catalog()` already does by hand,
  then saves a rollup blob via `self.save_catalog(blob, name="glyph_rollup")`
  (the base class's own storage convention — `sentinels/glyphs/catalogs/`,
  NOT the legacy `glyph_catalog.json` path, which stays completely untouched).
- `health_status()` — reads the last **cached** rollup via
  `self.load_catalog(name="glyph_rollup")`. Deliberately does **not** call
  `scan_source_tree()` fresh. `gather_health()` runs on the cockpit's 8s
  strip-refresh cadence in 4 places; a fresh ~3s full-tree walk on every
  call would reintroduce the exact GIL-contention regression already
  root-caused and fixed twice this session (`aria-security-strip-wire`,
  `aria-vessel-health`) — proactively avoided here rather than
  rediscovered a third time.
- `proposals()` / `coverage_gaps()` — read straight from the
  `SentinelReport.details` dict `scan()` already populated.
- Registered via `@register_sentinel`, wired into `stewardship/__init__.py`
  via the same `-import-d` anchor idiom every other sentinel this session
  uses.

**Purely additive.** No existing free function, dataclass, or `__all__`
export is touched, renamed, or removed — confirmed by a dedicated test
(`test_dunder_all_untouched_names_still_present`) and by re-importing all 4
legacy call sites post-patch (`test_legacy_call_sites_still_import_cleanly`).

## Files

- `patcher.py` — `patch_glyph_sentinel(text)` (adds the class + registration
  imports to `glyph_sentinel.py`) and `patch_stewardship_init(text)` (adds
  the one registration-import line to `stewardship/__init__.py`). Both
  anchored, idempotent (`MARK = "glyph-sentinel-migration-d"`), raise
  `PatchError` on a missing/duplicated anchor rather than silently no-op.
- `tests/test_patcher.py` — structural tests against the patch functions
  themselves (applies cleanly, idempotent, compiles, adds the right
  symbols) — no import of the patched module needed.
- `tests/test_glyph_sentinel_migration.py` — behavior tests against a
  **shadow copy** of the whole `sovereign_agent` package (never touches
  real `src/`). Staged only, never promoted — mirrors this session's own
  established pattern (`aria-vessel-health`, `aria-security-strip-wire`)
  for avoiding the `sys.modules`-pollution bug class found and fixed
  earlier this session.
- `tests/test_glyph_sentinel_migration_live.py` — the promoted copy: plain
  imports of the real post-apply module, zero `sys.modules` manipulation.
  This is the file the apply script copies into live `tests/`.
- `apply_glyph_sentinel_migration.sh` — guard → backup → patch → compile
  check → import/registration check → promote the live test file → run.

## Verify

```
.venv/bin/python -m pytest aria-glyph-sentinel-migration/tests/test_patcher.py \
  aria-glyph-sentinel-migration/tests/test_glyph_sentinel_migration.py -q
```

## Apply

```
./aria-glyph-sentinel-migration/apply_glyph_sentinel_migration.sh
```

Reversible: restore `stewardship/glyph_sentinel.py` and
`stewardship/__init__.py` from the timestamped `backups/` dir the script
creates.
