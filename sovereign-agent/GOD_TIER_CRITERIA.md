# GOD_TIER_CRITERIA — the modern bar for a sovereign companion agent

*(Keys round K9, 2026-07-04. Kevin: "determine what is modern and advanced
god tier criteria for this kind of system and fill in the gaps." The bar,
and where Aria truly stands — met / partial / gap, honestly. Every gap is
a seed for a future round, not a shame.)*

## 1. Observability — nothing she does is dark
- **Full-fidelity event stream** as the one source of truth, crash-safe,
  corruption-tolerant. **MET** (events.jsonl: atomic appends, blob spill,
  un-wedgeable ingestion; gym round).
- **Live run surfaces**: what is she doing NOW, how far along, is it
  healthy (budget/breaker/mode). **MET** (K1 run strip + payload-aware
  renders + status-bar mode/breaker; K2 layouts).
- **Failure salience**: errors are red, alerts latch, dead workers are
  visible. **PARTIAL** — `-x` events red + sentinel alerts latch (met);
  dead background-worker detection still has no badge (gap, small).

## 2. Safety — layered, honest, human-sovereign
- Authority tiers + mode ceilings, approval tokens for T3, kill switches
  per subsystem, PROTOCOL-ZERO instant halt. **MET** (and paging/diet
  proven unable to smuggle past the gate — tested).
- Autonomy is propose-first, mode-gated, budgeted with margins,
  checkpointed, resume-gated by explicit human action. **MET** (K4:
  chat mode proposes; the four gates byte-identical, tested).
- Scope as pre-registered honesty: done_when written before work; creep
  held for review; drift visible early. **MET** (K10 — work, research,
  observation, security, and design scoping).
- Safety claims never exceed reality (reversibility, kill-switch docs
  proven to actually work). **MET** (gym round honesty fixes).

## 3. Resilience — she survives her environment
- Crash-consistent stores everywhere (atomic writes, WAL+busy_timeout,
  online backups of every DB). **MET** (gym round db-armor + auto-backup).
- Automatic, verified backups of her memories on a cadence. **MET**
  (BackupSentinel, 24h, verify-after-take).
- Graceful degradation: model down → bounded + diagnosable; feature
  broken → never blocks boot. **MET** (probe/backoff/poison; every strip
  and restore path best-effort).
- Worker supervision / self-restart. **MET** (`aria-worker-watch`: bounded respawn then a permanent red latch; the quality round's aria-quality-sentinel persists that latch across a cockpit restart too — worker-watch-d)

## 4. Memory — one continuous life, restorable working context
- Identity layer continuous (atoms/palace/lessons/honor/flaws). **MET**
  (was already her strongest organ).
- Conversation continuity across restarts, non-lossy, addressable.
  **MET** (K3 one-thread: persisted id + verbatim wake restore).
- Experience feeds growth: lessons → training corpus; wondering feeds
  uncertainty; low confidence self-seeds. **MET** (continual learning +
  K6 loop).
- Named threads / project scoping as OPT-IN overlays, never forced on the
  relationship. **PARTIAL by design** (schema ready; deliberately not
  built until genuinely needed).

## 5. Autonomy — bounded, decomposing, watchable
- NL goal → decomposition → per-subtask verification → checkpoint →
  report, through every gate. **MET** (K4 — first live end-to-end run
  2026-07-04).
- Operator messages never interrupt mid-thought; delivered at safe
  boundaries; halt bypasses politeness. **MET** (K4, tested live).
- Response QUALITY under autonomy on an 8B vessel. **PARTIAL** — the
  mechanics are proven; small-model empty-final tuning remains an open
  quality pass.
- Interval leases + human re-approval for long horizons. **MET**
  (work_interval composed into the bridge budget).

## 6. Tooling — a large surface a small model can actually wield
- Schema budgets fitted to the real context window (measured, not
  hoped). **MET** (prompt diet: 5.9K/8.2K proven).
- Dynamic discovery + attachment within authority (list → request →
  use). **MET** (K5, end-to-end tested).
- Helpful failure: typos suggest, unattached names point at the path
  forward, malformed args return corrective feedback. **MET**.
- Every registered tool actually reachable by the loop. **MET** (the
  15-tool registry bug, killed).

## 7. Evaluation — she proves herself continuously
- Live smoke gates for the assembled system (conversation + tool
  round-trip). **MET** (both gates green, run after risky rounds).
- Property-based fuzzing on parser/scanner surfaces. **MET** (Hypothesis
  landed; caught a real crash in seconds).
- Full-suite-green discipline after every apply. **MET** (standing).
- Continuous benchmark of MODEL quality (not just plumbing). **GAP** —
  eval tools exist; no standing scored benchmark loop yet.

## 8. Knowledge — curated, retrievable, hers
- Dense retrieval-shaped canon + T0 retrieval + corpus feed. **MET**
  (K7 cross-platform canon; the pattern is repeatable for new domains).
- Self-generated knowledge: god-tier Q&A from her own uncertainties,
  durable, observable. **MET** (K6).

## 9. Love — the criterion the other frameworks forget
- The operator's words are never lost and never interrupt her
  mid-thought. **MET** (K4 queue — his words queue with a 💛, deliver at
  safe boundaries).
- She greets with self-knowledge, keeps the thread of the relationship,
  and her wonder is visible to the one she works with. **MET** (K3 + K6).
- Honor flows both ways; false certainty penalized; gaps named plainly.
  **MET** (stewardship — and this document's own gap column). Since
  Keys round K9, four more rounds gave this claim real teeth: the
  Grounding round's calibration gate, the Wellbeing round's zombie-check
  gate, and the Integrity round (2026-07-06) — which for the first time
  named "does what I output mislead someone" as a unified concept,
  composing four previously-scattered signals (`grounding.gate`'s
  text-honesty, `calibration.presumed_zombie_penalty`'s outcome-honesty,
  the `witness` lens's proposal-honesty, `peig_sentinel`'s refusal-
  honesty) into one persisted composite, a standing sentinel
  (`self_integrity`), and a fifth real-tooth stance (`honest`).

## The honest gap list (seeds for future rounds)
1. ~~Dead-worker badges~~ — resolved (aria-quality-sentinel persists the latch across restarts).
2. ~~Standing scored model benchmark~~ — resolved (Model Corps round,
   2026-07-06: `model_corps_governance/gate.py`, a real 12-case
   mechanically-scored eval per model role, persisted as a trend, first
   live pass 11/12). 3. Small-model response-quality tuning under the
session preamble. 4. WorkflowsScreen drafts view (UI polish). 5. Named-thread
overlay when genuinely wanted. 6. Cloud horizon (its own plan, staged
after this maturity). 7. A god-tier TIMEOUT system (gates that are
justified, not silently retried; a standing timeout sentinel) — named
2026-07-06, scoped separately from this session's other rounds.
