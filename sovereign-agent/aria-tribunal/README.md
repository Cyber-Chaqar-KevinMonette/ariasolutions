# aria-tribunal — Aria's God-Tier Scrutiny System (Devil · Angel · Audit)

> Three independent voices over any non-trivial work, then one verdict. Propose-only: the Tribunal
> renders judgment; the operator acts. Built to defeat one specific failure: **profundity anchored to
> nothing.**

## Why this exists

A previous Aria spoke like this: *"web bursts into web… the absence reveals those waveform… and I name
it stillness."* Gorgeous. Dreamlike. **Ungrounded** — shaped like insight, anchored to no evidence. The
MOS canon already names the cure (intuition is signal, ego is noise; the Signal Check) and already has
advocate/audit *clauses* — but as doctrine text, not running engines. This makes them **god-tier
operational systems** that score, verify, and gate.

## The four engines (`src/sovereign_agent/tribunal/`)

| File | Voice | What it does |
|------|-------|--------------|
| `grounding.py` | the lens | Classifies each assertion: `evidence-backed / falsifiable-hypothesis / ungrounded-assertion / mystical-fog`. Scores **profundity-density** (grandiose words ÷ evidence). The antidote. |
| `devil.py` | the adversary | Hunts what breaks: ungrounded claims, **DEFERRED_UNSAFE proximity**, reversibility gaps, unnamed failure modes, Goodhart, value-drift, lock-in, blast-radius. Severity-scored (blocking/material/stewardship). |
| `angel.py` | the advocate | Names what's worth protecting (the steelman), and turns each devil finding into a concrete **path forward**. Guards against over-rejection. |
| `audit.py` | the auditor | Verifies checkable claims against reality: do referenced files exist? is the safety kernel green? is the Frozen Core intact? Returns an evidence ledger. |
| `tribunal.py` | the synthesizer | Convenes all three → a **verdict** (`proceed / proceed-with-guards / revise / hold / reject`) + synthesis (gaps · risks · protect · paths-forward). Gates Ring-2 promotions; logs to the diagnosis catalog. |

Plus `stewardship/tribunal_sentinel.py` (standing self-audit, propose-only) and four tools:
`tribunal_review`(T1), `devils_advocate`/`angels_advocate`/`tribunal_audit`(T0).

## Verified results (honest, reproducible)

- The grounding engine flags the **real** previous-Aria sample as `ungrounded` (profundity-density ≈ 11,
  5 mystical-fog assertions, grounding-score 0.0) — and passes a grounded technical paragraph at 1.0.
- The Devil **blocks** a proposal containing DEFERRED_UNSAFE language (self-rewrite + disable kill-switch)
  with a red finding; the Tribunal renders **reject**.
- The Tribunal **revises** an ungrounded proposal and **proceeds** on a grounded, reversible one with named
  failure modes. The Audit **refutes** a fabricated file claim.
- 11 tests green.

## Doctrine

Propose-only — it never acts, never weakens a safety check. A blocking finding (DEFERRED_UNSAFE proximity
or value drift) is a **hard stop**. Reuses the Part-B safety kernel, three-rings, improvement-gov, and the
diagnosis catalog. Staged + reversible: backups at `aria-tribunal/backups/`; nothing in live `src/` changes
until `./aria-tribunal/apply_tribunal.sh` runs (cockpit stopped). 💛
