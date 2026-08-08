# aria-timeout-wing — proving wing + close-out (Timeout round · T4)

The stick before any tuning, for the T1-T3 machinery, following the exact
Q5/G5/W5/I5 wing shape. Five real, mechanically-scored tasks, no LLM
judge — fixture events are written directly into a tempdir's own
`events-<date>.jsonl` file rather than through the real global
`emit_event()`, so the proving suite never pollutes production data:

1. **timeout-scan-persists** — a scan over a justified fixture round-trips
   through T1's ledger.
2. **timeout-gate-blocks** — T2's `gate()` BLOCKs a fixture with 3
   repeated unexplained timeouts for the same tool.
3. **timeout-diagnosis-readable** — T3's standing sentinel logs a real,
   readable `TMOT-*` case into the diagnosis catalog.
4. **timeout-catalogued-justified** — a known-bounded source (git_tools,
   within its 15s bound) scores justified.
5. **timeout-uncatalogued-unexplained** — an uncatalogued source scores
   unexplained, never silently assumed fine.

## Wiring

`proving_ground/runner.py` — same tail-import pattern every prior wing
uses. `SUITE_VERSION` bumps `v7 → v8`.

## Round close-out

This is the last workstream of the Timeout round's ledger/gate/sentinel/
wing quartet (T5, the pytest-chunking script, is standalone). The apply
script runs the full offline proving suite as its own final check.

## Verify / Apply

```bash
./scripts/verify_module.sh aria-timeout-wing
./aria-timeout-wing/apply_timeouts.sh
```
