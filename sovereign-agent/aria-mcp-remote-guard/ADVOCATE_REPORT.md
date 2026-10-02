# Advocate report — aria-mcp-remote-guard (2026-10-02, Cloud Claude)

`./scripts/pre_apply_gate.sh aria-mcp-remote-guard` → **GATE: a voice says STOP.** Kevin decides whether
to apply. Every STOP and WARN is answered below.

| Voice | Verdict | Answer |
|---|---|---|
| Tribunal | proceed-with-guards (0.7) | Its risk, "sweeping scope, large blast radius", comes from replacing all of `mcp_server.py`. The actual diff to that file is small: a policy check in 2 tools, plus `build_remote_app()` and a guarded `main()`. The apply script backs up the original and restores it automatically if compile or tests fail. A dry-run apply plus rollback on a throwaway copy restored the file byte for byte. |
| Advocate Spectrum (council of ten) | **proceed** (0.44), champions: healer, artisan; opposed: none | — |
| 14-gen foresight | carry-forward; reversible, no lock-in | — |
| Quality gate | **BLOCK**, 95/100 (was 71.6 before this report's fixes) | **Fixed:** the observability block (every file now emits audit events through `safe_emit_event`) and the input-validation block. **Remaining:** "has tests" for `middleware.py`. The gate only searches the live `tests/` folder, which can't contain a test for a brand-new file before apply. `tests/test_mcp_guard.py` (21 tests) exercises the middleware and is copied into `tests/` by the apply script, after which this check passes. Kevin's call whether that's acceptable. |
| Grounding gate | WARN (mixed, 0.59) | The README's numbers are measured and reproducible (421 / 200 on the live server; 21 tests; a mutation test where 3 tests fail with the guard removed). The README's "honest limits" section names what was not tested: a live claude.ai connector and a real tunnel. |
| Integrity gate | WARN, "names no one it affects" | The README has a "Who it affects" section (Kevin, Aria, anyone who finds the URL). The heuristic didn't pick it up; left as is rather than rewording to game it. |
| Timeout gate | PASS | — |

## Latest run (v6.5.0 port)

Re-run 2026-10-02 after the **v6.5.0 port and default-deny gate**: Tribunal proceed-with-guards; council **proceed** (0.5); foresight carry-forward; quality 95/100, BLOCK only on the structural "has tests" check for the new `middleware.py`; **grounding PASS** (was WARN); integrity WARN; timeout PASS.

## Raw gate output (latest run)

```
════════ PRE-APPLY GATE: aria-mcp-remote-guard ════════
── Tribunal ──
   VERDICT: proceed-with-guards  (confidence 0.7)  · grounding: grounded
   Material risks present but addressable. Proceed with the named guards.
   risk: [stewardship] Sweeping scope — large blast radius. Prefer the smallest reversible step.
   → [blast-radius] Shrink the change to the smallest reversible step; expand only after it's vindicated.
── Advocate Spectrum (council of ten) ──
   VERDICT: proceed  · council 0.5  · champions ['healer', 'artisan']  · opposed []
── 14-Generation Foresight ──
   VERDICT: carry-forward  · base 1.4 · gen7 1.05 · gen14 0.7
   signals: {'lock_in': 0, 'reversible': True, 'value_markers': 2, 'blast_radius': 1, 'value_drift_risk': False}
── Quality Gate ──
   ✗ quality gate: BLOCK · 4 file(s) · 95.0/100
  · BLOCK: aria-mcp-remote-guard/payload/src/sovereign_agent/mcp_guard/middleware.py failed critical check(s): has tests
── Grounding Gate ──
   ✓ grounding gate: PASS · verdict=grounded · 0.60
── Integrity Gate ──
   ⚠ integrity gate: WARN · 0.63
  · witness: names no one it affects — surface the impact
── Timeout Gate ──
   ✓ timeout gate: PASS · 0 unexplained
  · nothing to check
──────────────────────────────────────
GATE: a voice says STOP — review before applying
```
