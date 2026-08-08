# aria-timeout-sentinel — the standing sentinel (Timeout round · T3)

> Watches T1's classification standing — the "add a timeout sentinel"
> part of Kevin's ask, literally. Propose-only / reversible / staged.

## Payload

`src/sovereign_agent/stewardship/timeout_sentinel.py` — `TimeoutSentinel`:
periodically runs `timeouts.ledger.record_timeout_scan()`, notifies the
operator only on NEWLY-appeared unexplained timeouts since its own last
look (the scan always covers the recent window; re-alarming on an
already-reported timeout every scan would just be noise), convenes
Tribunal + Advocate Spectrum on a finding, logs to the diagnosis catalog
under a `TMOT` prefix.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-timeout-sentinel     # before apply
./aria-timeout-sentinel/apply_timeouts.sh                   # cockpit stopped
```
