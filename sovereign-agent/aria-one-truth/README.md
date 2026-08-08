# aria-one-truth — the cross-store consistency sentinel (FABLE II · M1)

> Her memory is many excellent organs; the next failure class is not loss,
> it is DISAGREEMENT. This organ checks the JOINS the way loose-threads
> checks the calls. One life, one truth. Propose-only / reversible / staged.

## The joins (each = one named check, mechanical verdict)
- `thread-chunks` — thread_id ↔ chunks.ndjson agree on THE thread
- `sessions-scope` — every `sessions/<sid>.scope.json` has its session
- `active-corpses` — no session claims "active" with no process for > 24h
- `rest-point` — resume_point.json names a real, resumable session
- `lessons-retrain` — atoms.db lessons count ↔ retrain marker (never ahead)
- `qa-uncertainty` — qa.ndjson low-confidence answers opened their
  uncertainties; no dangling closes in the registry
- `proving-suite` — every proving result references its suite version
- `dispositions` — loose-threads dispositions reference symbols that still
  exist (RETIRED-then-deleted is the one honest exception)

Findings carry repair PROPOSALS (the diagnosis.py pattern) — nothing is
ever auto-repaired. Health is warn-level: disagreement is drift, not fire.

## Payload
- `src/sovereign_agent/consistency/checks.py` — the joins
- `src/sovereign_agent/consistency/sentinel.py` — ConsistencySentinel
  (`one-truth`, kill switch `SOV_NO_ONE_TRUTH_SENTINEL`)
- `src/sovereign_agent/consistency/__main__.py` — `python -m
  sovereign_agent.consistency scan|health`
- patcher: registers the sentinel + adds `sov truth [--json]`

## Verify / Apply
```bash
./scripts/verify_module.sh aria-one-truth      # before apply
./scripts/safe_apply.sh aria-one-truth         # cockpit stopped
```
