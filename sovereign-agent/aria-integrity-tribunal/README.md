# aria-integrity-tribunal — standing sentinel + witness lens override (Integrity round · I3)

> Watches I1's composite score standing, and lets the Advocate Spectrum's
> witness lens prefer measured data over a one-shot regex heuristic.
> Propose-only / reversible / staged.

## Payload

- `src/sovereign_agent/stewardship/self_integrity_sentinel.py` —
  `SelfIntegritySentinel`: periodically runs `integrity.ledger.
  record_integrity_pass()` over recently-written journal entries and QA
  answers, reusing `grounding_sentinel.py`'s exact recent-text sourcing
  (`_recent_journal_texts`/`_recent_qa_texts` — composed, not duplicated).
  Convenes Tribunal + Advocate Spectrum over the same recent work, logs to
  the diagnosis catalog under an `INTG` prefix. Named `self_integrity_
  sentinel.py` (not `integrity_sentinel.py`) to avoid colliding with the
  pre-existing host/malware integrity monitor of that name.
- **Changed**: `spectrum/lenses.py`'s `witness()` — prefers the persisted
  `integrity_verdict`/`integrity_score` composite over the live-only
  harm/deceive regex when present, same measured-data-override pattern
  `skeptic`/`angel` already use. Byte-identical fallback otherwise.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-integrity-tribunal     # before apply
./aria-integrity-tribunal/apply_integrity.sh                 # cockpit stopped
```
