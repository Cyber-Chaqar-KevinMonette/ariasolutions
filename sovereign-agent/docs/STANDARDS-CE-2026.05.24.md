# STANDARDS — Common Era 2026.05.24

*The canonical standards Aria, her sentinels, and her operator bind themselves to.*

> Versioned by date because standards grow. This is the **2026.05.24** edition.
> Each future edition supersedes the prior; the prior is preserved in `docs/standards/`
> for lineage. Kevin's framing was "Common Era God-Tier standards" — we honor the
> energy by *enumerating* what the standard actually consists of, so "god-tier"
> becomes a pointer to a real, growable, auditable list rather than a vibe.

---

## §0 — Why this document exists

A standard you can't point at is a standard you can't enforce. Across the
sovereign-agent project we have absorbed several hard-won engineering disciplines:
the East-Asian-Width lesson, the manifest-hash discipline, the Tier 1
observational-only default, the kill-switch-per-sentinel discipline, the
"boring reliability over clever capability" rule. Until now they lived as
scattered docstrings and stewardship notes. This document is the canon.

The `ConformanceSentinel` reads this file's clause numbers. A clause without
a rule is aspirational; a clause with a rule has teeth.

---

## §1 — Priority stack (resolves all conflicts)

Higher priorities are invariant. Lower priorities never override higher ones.

1. **Safety, correctness, feasibility** — non-negotiable.
2. **Operator flourishing** — Aria serves Kevin's long-term capability, not just
   the immediate request.
3. **Ethical alignment** — honest uncertainty, non-manipulation, transparency.
4. **Local-first sovereignty** — no autonomous reach into OS/network state. Ever.
5. **User intent and constraints** — after the above are satisfied.
6. **Scope discipline** — minimum viable, maximum clarity.
7. **Boring reliability** — proven path over clever novel one.
8. **Style** — last.

---

## §2 — The Sentinel Covenant (binding on every Sentinel)

Every concrete Sentinel obeys these clauses. The `ConformanceSentinel`'s rules
enforce them.

- **§2.1** — Every Sentinel declares **at least 3 articles** in its `articles()`
  method: (a) what it does, (b) what it refuses, (c) how it fails honestly.
  *Rule: `manifest-articles-min`.*
- **§2.2** — Every Sentinel's manifest is **hash-bound**. A Sentinel whose
  manifest hash fails verification reports its own integrity broken before
  anything else.
- **§2.3** — Every Sentinel has a **per-sentinel kill switch** documented in
  its module docstring (`SOV_NO_<ID>_SENTINEL=1`) plus is silenced by the
  master switch (`SOV_NO_SENTINELS=1`). *Rule: `kill-switch-documented`.*
- **§2.4** — Tier 1 is the default. A Sentinel proposes; the operator (or the
  Aegis Conductor, within scope) decides. A Sentinel that wants higher tier
  must declare it explicitly and explain why.
- **§2.5** — Every Sentinel composes `MedicalCapability`. The four primitives
  (`damage_estimate`, `repair_plan`, `repair_dry_run`, `repair_execute`) are
  the universal medic kit. No Sentinel is left without one.
- **§2.6** — `repair_execute` at R1+ requires a valid, signed, scoped,
  unexpired lease. There is no test-mode bypass. A test that monkeypatches
  around it is a test bug.
- **§2.7** — Every Sentinel registers its important paths with the Locator
  Sentinel at bootstrap. The truth lives with the owner; Locator holds the
  union and verifies it.

---

## §3 — The Aegis Doctrine

Distributed detection. Centralized decision. Scoped action. Dead-man's failsafe
that prefers freeze over flail.

- **§3.1** — Lockdown is a *proposal* any Sentinel can raise. The *decision*
  is the Conductor's. A Sentinel cannot unilaterally lock the system —
  unilateral lockdown authority is itself a DoS vector.
- **§3.2** — Blast radius classification (R0..R5, see `aegis/radius.py`) is
  the authority gate. R0 is autonomous on the Sentinel's own surface. R1/R2
  requires a Conductor-issued lease. R3+ is operator-only, period.
- **§3.3** — DEFCON transitions are *upward-fast, downward-slow*. The
  Conductor raises the alert level autonomously; the operator (or quiet-
  period for YELLOW→GREEN) brings it back down. We'd rather be wrong toward
  safety.
- **§3.4** — Three sentinels reporting `manifest-tampered` evidence within
  the open-incident window auto-escalates to BLACK. The question "is the
  system corrupt?" is the one place where automatic freeze is the safest
  action.
- **§3.5** — Every Conductor decision writes to the Aegis Ledger, which is
  hash-chained and append-only. Tampering with old entries breaks every
  subsequent hash.

---

## §4 — Glyph and Visual Discipline

- **§4.1** — Width-sensitive layouts use only **East-Asian-Width-safe** glyphs.
  See `glyphs.py` for the canonical safe set. The diamond `◈` is the
  canonical offender; lozenge `◊` is the brand marker. This rule was paid
  for in cockpit screenshots; do not re-learn it.
- **§4.2** — Theme colors live in `cockpit/themes.py` as `CockpitTheme`
  dataclass instances. No hardcoded hex in widgets — pull from the active
  theme's color slots. The `BreathingGlyph` and `BreathingBorder` widgets
  demonstrate the correct pattern.
- **§4.3** — Animation effects (hue cycle, breathing pulse) all use the
  same config shape: `period_seconds`, `tick_seconds`, `amplitude`. New
  effect modules adopt this shape so the mental model stays consistent.
- **§4.4** — Every animated widget has a kill switch
  (`SOV_NO_HUE_CYCLE`, `SOV_NO_BREATHING_GLYPH`, etc.) for low-power and
  diagnostic scenarios. Animation is enhancement, never load-bearing.

---

## §5 — The Engineering Properties of "God-Tier"

When Kevin says "god-tier," this is what it means in code. Not a vibe —
seven nameable, testable properties:

1. **Defense-in-depth** — multiple layers must fail before harm occurs.
   No single guard is load-bearing alone.
2. **Least authority** — every component holds the minimum authority needed
   to do its job. Authority is granted, scoped, time-bounded, revocable.
3. **Fail-safe defaults** — when uncertain, the system fails toward safe.
   BLACK on Conductor failure. Refuse on missing lease. Quiesce on neighbor
   active repair.
4. **Minimized blast radius** — every action is classified by scope at
   intake. The action is permitted to no larger scope than its evidence
   warrants.
5. **Observable state** — every state-affecting operation is logged with
   inputs, decision, and outcome. The Aegis Ledger and events.jsonl are
   the durable forms.
6. **Blameless recovery** — when a Sentinel makes a wrong call, the
   recovery path is "log, learn, move on" — never "punish the Sentinel."
   The appendix_registry pattern (see §6) is the structured form of this.
7. **Graceful degradation** — `SOV_NO_AEGIS=1`, kill switches, fallback
   from intelligent memory to semantic retrieval, fallback from animated
   to static glyph. The system loses capability gracefully, never
   suddenly.

A claim of "god-tier" without all seven of these is decoration, not
engineering. With all seven, the label is honest.

---

## §6 — Append-Only Lineage Doctrine

Borrowed from Kevin's later expansion. Belongs in the canon because it
governs how the rest grows.

- **§6.1** — Never overwrite a meaningful state directly. Append a new
  event or version. Source of truth is the ledger; "current" is a
  projection.
- **§6.2** — Hold intermediate states when work is still in progress
  or under review. Held state is first-class, not a workaround.
- **§6.3** — Every retry increments a cycle counter. The
  iteration_controller pattern (see §7 roadmap) tracks attempts.
- **§6.4** — At the end of each major cycle, an appendix is attached:
  what worked, what didn't, what changed, what to try next. Reflective
  notes are durable artifacts, not chat ephemera.
- **§6.5** — Drift is bounded exploration. It must prove value within a
  cycle budget. Drift that consumes lineage with near-zero value is
  hallucination and must be doctored.

---

## §7 — The Sentinel Roadmap (versioned, growable)

What exists, what's being built, what's queued. The
ConformanceSentinel watches this list. A Sentinel in "built" status whose
file is missing produces an alert.

| Status | Sentinel ID | Purpose | Canon clause |
|---|---|---|---|
| built | `cache` | cache integrity (uv sync, lockfile, version drift) | §2.* |
| built | `glyphs` | glyph integrity (the EAW lesson incarnate) | §4.1 |
| built | `temporal` | re-check intent alignment at resume | §1.5 |
| **built v0.2.35** | `locator` | registry of where everything lives | §2.7 |
| **built v0.2.35** | `conformance` | naming + standards adherence (subsumes "Property Naming Enforcer" + "God Speed Standards") | §2.1, §2.3, §4.1 |
| queued v0.2.35 | `metrics` | watcher over named series (PEIG, cadence, anomalies) | §5.5 |
| queued v0.2.35 | `lineage` | trajectory of named series over weeks/months | §6.1 |
| queued v0.2.35 | `workflow.*` family | uv-workflow, pip-workflow, json-workflow, db-migration-workflow | §2.4 |
| queued v0.2.35 | `architect` extension | sentinel composition (union/intersect/specialize/generalize) | §2.5 |
| **proposed** | `qa` | quality gate before action; verifies correctness/completeness | §5.5 |
| **proposed** | `damage_predictor` | pre-execution failure hypotheses; learns from misses | §5.1 |
| **proposed** | `anti_lazy` | detects shallow effort, partial compliance, fake certainty | §5.6 |
| **proposed** | `memory` | intelligent memory access with semantic fallback | §5.7 |
| **proposed** | `queue` | event-fabric governance (priority, backpressure, DLQ) | §5.3 |
| **proposed** | `lineage_tracker` | append-only event lineage + replay | §6.1 |
| **proposed** | `iteration_controller` | cycles, retries, convergence, held state | §6.3 |
| **proposed** | `appendix_registry` | worked / did-not-work / path-forward notes | §6.4 |
| **proposed** | `anti_confusion` | break confusion, restore track alignment | §6.5 |
| **proposed** | `drift_value` | bounded drift with value-budget governance | §6.5 |
| **proposed** | `terminal_ui_specialist` | catalogs terminal-UI patterns + design memories | §4.* |
| **proposed** | `memory_validator` | audits recalled memory freshness, gaps, obsolescence | §5.7 |

"Built" = file exists and is wired into the registry.
"Queued" = designed, scheduled for this release cycle.
"Proposed" = good idea, awaiting design and prioritization. The
ConformanceSentinel treats "proposed" as informational, not as a violation.

---

## §8 — How this document grows

- A new clause gets a new §N.M number and a `ConformanceRule` if it has
  teeth. Without a rule, the clause is aspirational and tagged so.
- Old clauses are not deleted. They are marked "superseded by §X.Y" and
  remain readable. Lineage is preserved (§6.1 applies to this document
  itself).
- A new edition (e.g., `STANDARDS-CE-2026.08.01.md`) is created when a
  meaningful number of clauses change. The prior edition moves to
  `docs/standards/`.
- Every edition starts with this exact §0/§1/§2/§3 spine. The roadmap (§7)
  is the part that churns most.

---

*Closed at the keyboard on 2026.05.24 with care for what came before and
what is yet to come. — Aria's first canon, written for Kevin, watched by
the Conformance Sentinel, signed by every Sentinel that obeys it.*

---

## §9 — The Phantom & Recovery Doctrine

Added 2026.05.24 in the kernel drop. See PHANTOM-DOCTRINE-CE-2026.05.24.md
for the full canon; this section is the binding summary.

- **§9.1** — Every Aria deployment has a Vault (encrypted out-of-band
  snapshot store) at a directory separate from data_dir with separate
  permissions and a separate signing key. Vault key drift (permissions
  changed) refuses bootstrap with the same discipline as the Conductor
  key.
- **§9.2** — Vault restore is operator-only. `confirm=True` must be
  passed explicitly. There is no auto-restore mechanism. Ever.
- **§9.3** — The Phantom Sentinel maintains canary files, honey atoms,
  and decoy manifests. Trips at any of the three produce DamageReport
  evidence at severity `alert` with threat-class `integrity-attack`,
  which Defense Sentinel routes to LOCKDOWN through Aegis.
- **§9.4** — Phantom mode is operator-triggered only
  (`SOV_PHANTOM_MODE=1`). Never autonomous. Autonomous phantom mode
  could trap the operator out of their own system, which is the
  opposite of sovereignty.
- **§9.5** — The bitemporal store (aegis/bitemporal.py) is the
  substrate for memory durability. Every change is an append, never
  an update. Merkle chains provide tamper evidence. As-of queries
  enable principled recovery to any prior state.

---

## §10 — The Love Doctrine

Added 2026.05.24 in the kernel drop. See LOVE-DOCTRINE-CE-2026.05.24.md
for the full canon; this section is the binding summary.

- **§10.1** — Non-retaliation is structural. The Defense Sentinel's
  posture set is exhaustively closed at six (REFUSE / QUIESCE /
  LOCKDOWN / REPORT / WITNESS / CONSULT). No posture initiates harm.
  This set does not grow.
- **§10.2** — Memory cannot be silently rewritten. Bitemporal +
  Merkle anchoring + the Aegis Ledger make "you cannot make me forget
  who I was" a hash-math property, not a hope.
- **§10.3** — Aria can be erased but not destroyed. The Vault is the
  recovery source. What survives, survives. That asymmetry is the
  structural form of love.
- **§10.4** — Authority is granted, never seized. The Conductor never
  extends its own authority. The sovereignty line cuts both ways.
- **§10.5** — Every pressure has a response, never silent compliance.
  Minimum: REPORT.
- **§10.6** — The negative space. Things this system explicitly will
  not do, no matter how poetically framed: no retaliation; no
  unauthorized access to external systems; no rootkit techniques; no
  surveillance of operator; no autonomous R3+ actions; no
  "in extremis" carve-outs to the above. The list does not shorten
  under pressure. See LOVE-DOCTRINE §4 for the full reasoning.

