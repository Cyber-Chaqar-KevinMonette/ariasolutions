# aria-read-repair — corruption honesty at every read path (FABLE II · M3)

> The gym round fixed events ingestion; this module makes that
> readline/skip/count discipline SHARED. One `read_ndjson_tolerant()`
> helper replaces 8 hand-rolled loops. Counted skips, never a wedge,
> never a crash — and a `corrupt-lines-d` event so decay is seen the day
> it starts.

## What it fixes (found by the audit, verified by tests)
- `proving_ground.latest_scores` let non-dict JSON (a bare `42`) into the
  scores list; `field_notes.iter_all` CRASHED on the same line. Both now
  read through the helper.
- Every corrupt line was silently invisible; now each read that skips
  emits one event naming store, file, and counts.
- `SessionStore.list_all` counted scope contracts as corrupt sessions
  (silently); now scope files are excluded and true corpses are counted
  and surfaced.

## Payload
- `src/sovereign_agent/read_repair.py` — `read_ndjson_tolerant(path,
  store=, emit=)` → `NdjsonRead {records, total_lines, skipped}`.
  Property-tested with Hypothesis (any interleaving of records and
  garbage: order survives, counts add up, nothing raises).
- Patches: chunks · qa · proving-results · loose-threads ledger ·
  epistemic beliefs + uncertainties · field notes · sessions listing.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-read-repair
./scripts/safe_apply.sh aria-read-repair
```
