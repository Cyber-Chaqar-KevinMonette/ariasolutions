# aria-quality-sentinel — the persisted quality ledger (Quality round · Q1)

> `qa/hardening.py` + `qa/quality_score.py` were real and deterministic —
> just never written down. This is the same fix `proving_ground/` already
> applied to benchmarks: persist the score, then watch it.

## What it adds
- `src/sovereign_agent/quality/ledger.py` — `record_quality_pass(targets,
  data_dir)` runs `qa.hardening.harden_module()` per target, scores via
  `qa.quality_score.score_hardening_report()`, appends an fsync'd NDJSON
  record. A pass's `critical_ok` is true only if EVERY scored file passed
  its critical (weight-≥8) checks — one bad file never hides in an
  average. `latest_quality()` / `quality_trend()` read stored scores only.
- `stewardship/quality_sentinel.py` — `QualitySentinel` (`quality`, tier 1,
  propose-only): scans files changed since its own last look (git diff,
  bookmarked in its catalog), falling back to the newest applied module's
  payload on a fresh install. Warns on any critical failure. Kill switch
  `SOV_NO_QUALITY_SENTINEL`.
- Cross-session worker-latch persistence: `_persist_worker_latch()` writes
  `<data_dir>/cockpit/worker_health.json` alongside the existing in-process
  `_DEAD_WORKERS` set (`aria-worker-watch`, already live) — a worker death
  is now visible even after a cockpit restart clears the in-memory badge.
- Doc sync: `GOD_TIER_CRITERIA.md`'s "Worker supervision — GAP" line was
  stale (the gap was already closed by `aria-worker-watch`, which predates
  this round); corrected to MET, citing both.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-quality-sentinel
./scripts/safe_apply.sh aria-quality-sentinel
```
