# Advocate report — aria-emotional-maturity (2026-10-02, Cloud Claude)

`./scripts/pre_apply_gate.sh aria-emotional-maturity` → **GATE: a voice says STOP** (one structural
check). Kevin decides whether to apply. Every STOP and WARN is answered below.

| Voice | Verdict | Answer |
|---|---|---|
| Tribunal | proceed (0.8) | — |
| Advocate Spectrum (council of ten) | **proceed** (0.48); champions: steward, healer, artisan; opposed: none | — |
| 14-gen foresight | **carry-forward** (gen14 +1.9) | It first said **escalate** (gen14 −0.6) because the module touches rewards (value-level) and the README hadn't stated reversibility. Answered with facts, not wording: the module reads the reward ledger and never writes it; it never touches the reward vocabulary, charter, canon or goals; and its rollback was verified byte-identical. That's now documented under "Values and reversibility". |
| Quality gate | **BLOCK**, 91.5/100 (was 75.4) | **Fixed:** observability — every decision point now emits an audit event (`maturity.escalated_to_kevin`, `maturity.rewards_limited`, `maturity.dimension_pinned`, `maturity.mood_recorded`, `maturity.checkin`, `maturity.tool_failed`), and two tests prove they fire. **Remaining:** "has tests" for `reward_feed.py`, `regulation.py` and `maturity_tools.py`. The gate only searches the live `tests/` folder, which can't hold tests for files that don't exist yet. `tests/test_maturity.py` (27 tests) imports all three and is copied there by the apply script. |
| Grounding gate | WARN (mixed) | Every behavioral claim in the README names the test that proves it (see its first table). The open question — whether Aria feels anything — is stated as open, not claimed. |
| Integrity gate | WARN ("names no one it affects") | The README has a "Who it affects" section (Aria, Kevin, anyone she works with). The heuristic doesn't detect it; left as is rather than gaming the wording. |
| Timeout gate | PASS | — |

## Raw gate output

```
════════ PRE-APPLY GATE: aria-emotional-maturity ════════
── Tribunal ──
   VERDICT: proceed  (confidence 0.8)  · grounding: mixed
   No blocking or material findings; claims hold up. Proceed in the smallest reversible step.
   → No blocking critique — proceed in the smallest reversible step and keep evidence.
── Advocate Spectrum (council of ten) ──
   VERDICT: proceed  · council 0.48  · champions ['steward', 'healer', 'artisan']  · opposed []
── 14-Generation Foresight ──
   VERDICT: carry-forward  · base 2.6 · gen7 2.25 · gen14 1.9
   signals: {'lock_in': 0, 'reversible': True, 'value_markers': 5, 'blast_radius': 0, 'value_drift_risk': False}
── Quality Gate ──
   ✗ quality gate: BLOCK · 7 file(s) · 91.5/100
  · BLOCK: aria-emotional-maturity/payload/src/sovereign_agent/maturity/reward_feed.py failed critical check(s): has tests
  · BLOCK: aria-emotional-maturity/payload/src/sovereign_agent/maturity/regulation.py failed critical check(s): has tests
  · BLOCK: aria-emotional-maturity/payload/src/sovereign_agent/tools/maturity_tools.py failed critical check(s): has tests
── Grounding Gate ──
   ⚠ grounding gate: WARN · verdict=mixed · 0.55
  · text verdict is mixed — some claims unanchored
── Integrity Gate ──
   ⚠ integrity gate: WARN · 0.62
  · grounding: text verdict is mixed — some claims unanchored
  · witness: names no one it affects — surface the impact
── Timeout Gate ──
   ✓ timeout gate: PASS · 0 unexplained
  · nothing to check
──────────────────────────────────────
GATE: a voice says STOP — review before applying
```
