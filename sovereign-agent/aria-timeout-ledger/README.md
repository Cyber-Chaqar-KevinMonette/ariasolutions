# aria-timeout-ledger — the persisted timeout classification (Timeout round · T1)

> Reads the SAME existing `events.jsonl` ledger — no new storage — for
> timeout-flagged events and classifies each as justified (a known,
> catalogued, bounded timeout site) or unexplained. Propose-only /
> reversible / staged.

## Why

Kevin: "make sure timeouts become gates and justified... a god tier
timeout system." Research found the exact gap: `vram.py:117-161`'s
`vram_lock()` is the ONE mechanism in the whole tree that already both
times out and emits a durable ledger event on timeout — but nothing ever
reads that event back. Written once, forgotten. This closes exactly that.

## Payload

`src/sovereign_agent/timeouts/ledger.py` — `TIMEOUT_CATALOG` (every
known-bounded timeout site this round's research found: git tools 15s,
the resilience scanner's 2s SIGALRM, `vram_lock` 60s, LLM-call timeouts,
subprocess tool timeouts up to 600s — most don't yet emit an event;
`vram_lock` is the only real emitter today, and others slot into the same
catalog for free as they're wired up in the future). `record_timeout_
scan()` reads recent `events-*.jsonl` entries whose flag ends in
`"-timeout-d"` (a deliberately precise suffix match — a substring match
on "timeout" would recursively misclassify this module's own emitted
`timeout-scan-d` summary event as an unexplained timeout, caught by a
dedicated test), classifies each, persists an NDJSON pass. `latest_
timeout_scan()` / `timeout_trend()`.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-timeout-ledger     # before apply
./aria-timeout-ledger/apply_timeouts.sh                 # cockpit stopped
```
