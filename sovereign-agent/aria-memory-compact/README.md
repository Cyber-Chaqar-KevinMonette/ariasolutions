# aria-memory-compact — bounded growth with dignity (FABLE II · M2)

> Every append-only store grows forever. Compaction here NEVER loses
> meaning: cold storage with a pointer, not summarize-and-discard.
> Propose-first / operator-executed / kill-switched / reversible.

## How it works
- **Audit** (`sov compact audit`): sizes + growth rates for every
  registered store (chunks, qa, field-notes, proving-results,
  calibration, interpretations, + the audit-only ledgers) and journal/.
- **Compactable vs audit-only, honestly**: stores whose readers reduce
  over FULL history (beliefs, uncertainties, loose-threads, honor,
  behavior-patterns) are audit-only with a written reason — moving their
  records would change what a read returns.
- **Compact** (`sov compact preview|run <store> [--before-days N]`,
  default 180): records older than the cutoff move RAW-LINE-VERBATIM to
  `<store>.cold-YYYY-MM.ndjson`; the hot file is rewritten atomically
  (timestamped .bak kept); `compact_index.json` is the pointer — period →
  cold file, count, mechanical digest. Undatable/corrupt lines never move.
  A count verification restores the original on any mismatch.
- **Addressability kept**: `ChunkStore.get_chunk` falls back to cold files
  on a hot miss (patched) — a compacted chunk is still reachable by id.
- **Kill switches**: `SOV_NO_COMPACT=1` master, `SOV_NO_COMPACT_<STORE>=1`
  per store.
- **MemoryCompactSentinel** (`memory-compact`): conservative thresholds,
  proposes the exact `sov compact` commands, never executes.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-memory-compact
./scripts/safe_apply.sh aria-memory-compact
```
