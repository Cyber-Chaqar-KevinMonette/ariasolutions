# The Signal — Sovereign System Design Charter

<!--
charter-version: 0.1.0
charter-hash:    sha256:441e95a4c063b8843edd4037c5754169b9180119a2357eb7ce6000407ce7a345
-->

*Seven articles. Mirrors the seven commitments. Read aloud before any
architectural decision in this tree.*

> **A system has the right to lie to its operator only if lying is impossible.**
> Everything below is engineering that closes one more lying-vector.

---

## I. No silent degradation

Every deviation from the happy path produces both a **loud signal** (a
visible mode flag, a banner, a doctor verdict) and a **quiet trail**
(structured events, traces, the append-only log). Returning success
without naming degradation is a defect class — the same severity as a
missing test or a corrupted migration. Code review rejects silently
degrading code.

## II. Provenance is born with the artifact

Every atom, snapshot, plan, install, deploy, file write, or decision
carries `(produced_by, produced_at, tooling_versions, mode, depends_on)`
at the moment of creation. Provenance reconstructed after the fact is
suspect. If an artifact lacks provenance, it is treated as if its
provenance were `unknown` — which is worse than `degraded`.

## III. Bitemporal where memory lives

Records distinguish **event time** (when it was true in the world) from
**system time** (when we recorded it). Replay of past beliefs is a
first-class operation, not a forensic exercise. The question "what did
we believe at T?" must always be answerable, even when the answer is
"we don't know, and that lack-of-knowing is itself recorded."

## IV. Modes are explicit and composable

Every subsystem publishes a mode from a fixed lattice:

    normal  →  recovering  →  degraded  →  gray  →  quarantined
                                                  ↘
                                                   unknown

Consumers inherit the taint of their dependencies. `unknown` is treated
as **worse than `degraded`**, because a known-bad system can be worked
around; an unknown one cannot. Mode transitions emit events on the
audit log; mode is queryable through doctor.

## V. The doctor's verdict binds

When `sov doctor` reports a charter-integrity violation, the CLI
refuses to dispatch anything except `sov doctor` and `sov charter`.
That is the kill switch — Article V made mechanical, not aspirational.
Operators may amend (explicitly, with a recorded amendment event).
Agents may not. The doctor is the source-of-truth for the system's
self-assessment; nothing in the tree may shadow it with a quieter
opinion.

## VI. Stewardship is bounded

Agents may **propose** remediations for degraded state. Stewardship
agents are capped at **Tier 1** (reversible writes — opening proposals,
writing to the `gaps` channel, annotating dashboards). Tier 2+
remediation requires operator confirmation. Stewardship may not
escalate its own authority — an agent that grants authority to another
agent has bypassed the authority model and PROTOCOL-ZERO fires.

The system fights its way back to sovereignty; it does not seize
authority in the name of fighting.

(Tier semantics match `router.py`: tier numbers increase with capability
and risk. Tier 0 = read-only, Tier 4 = cross-system orchestration. This
is the *single* canonical tier model in the tree.)

## VII. Unexplained success is suspicious

A successful outcome with missing provenance, unknown upstream mode, or
untraceable inputs is **downgraded, not trusted**. Quiet wins are
scrutinized before they are banked. The hardest failure mode to catch
is the one where everything reports green and nothing actually worked
— this article exists to make that mode pay the same costs as a loud
red.

---

## Reversibility as a cross-cutting property

Reversibility is *not* an eighth article. It is a property every
operation declares about itself, sitting under Articles II, IV, and VI:

| Class | Meaning | Required guard |
|---|---|---|
| `transactional` | True undo via snapshot/rollback inside system boundaries | Tier 0–2; must complete or rollback as a whole |
| `compensating` | Saga-style: each forward action has an explicit registered inverse | Tier 1–3; inverse must exist in `rollback.py` registry |
| `irreversible` | No undo; can only append more facts (sent email, charged card, deleted data) | Tier 3+ ONLY; must be preceded by all reversible prep; emits a loud event |

No Tier-1 operation may be `irreversible`. Every `irreversible`
operation must have a registered compensation-or-quarantine path.
Operations without a declared class default to `unknown` reversibility
and are blocked above Tier 1 until classified.

---

## Amendment protocol

This charter binds. The only legitimate way to change it is through a
structured amendment:

1. Edit the charter prose and/or YAML block.
2. Run `sov charter amend --rationale "<reason>"` — this:
   - Computes the new content hash.
   - Updates the `charter-hash` header in this file.
   - Writes a `charter_amendment` event to `events.jsonl` recording
     `version_before`, `version_after`, `hash_before`, `hash_after`,
     `rationale`, and `operator_acknowledged_at`.
3. The next `sov doctor` run validates: the new hash matches, the
   amendment event exists, and the YAML block remains internally
   consistent. If any check fails, the kill switch fires.

There is no escape hatch. No env var, no `--force` flag, no hidden
config option upgrades stewardship past Tier 1 or bypasses the
hash check.

---

## How this charter is checked

`sov doctor` runs `check_charter_integrity()` on every invocation:

- **File present?** If not → warning (`unknown` charter; pre-amendment
  migration path). Commands still run.
- **Hash matches?** If not → **error** (kill switch fires). Only `sov
  doctor` and `sov charter *` dispatch.
- **YAML block parses and matches prose?** Mode enum, tier caps,
  reversibility classes, `max_articles` constraint all enforced.
- **Article count ≤ `max_articles`?** Hard cap. Inflation is rejected
  at validation time.

The CLI's top-level callback queries the doctor's integrity check
before every dispatch. Article V is not a wish; it is the dispatch
mechanism.

---

## Version

v0.1.0 — initial ratification.

---

```yaml
# charter:v0.1.0 — machine-readable bindings
# Prose above is the source of truth for humans.
# This block is the source of truth for code.
# If they disagree, the disagreement IS the charter violation.

charter:
  version: "0.1.0"
  max_articles: 7
  articles:
    - id: I
      slug: no-silent-degradation
    - id: II
      slug: provenance-is-born-with-artifact
    - id: III
      slug: bitemporal-where-memory-lives
    - id: IV
      slug: modes-explicit-and-composable
    - id: V
      slug: doctor-verdict-binds
    - id: VI
      slug: stewardship-is-bounded
    - id: VII
      slug: unexplained-success-is-suspicious

modes:
  lattice:
    - normal
    - recovering
    - degraded
    - gray
    - quarantined
    - unknown
  unknown_worse_than_degraded: true
  inherit_taint_from_dependencies: true

tiers:
  model: "router.py canonical"
  direction: "numbers increase with capability and risk"
  range: [0, 4]
  stewardship_max_tier: 1
  irreversible_min_tier: 3

reversibility:
  classes:
    - transactional
    - compensating
    - irreversible
  default_when_undeclared: unknown
  irreversible_requires_registered_compensation: true

amendment:
  event_type: charter_amendment
  required_fields:
    - version_before
    - version_after
    - hash_before
    - hash_after
    - rationale
    - operator_acknowledged_at

kill_switch:
  triggers_on:
    - charter_hash_mismatch
    - yaml_prose_disagreement
    - article_count_exceeds_max
  permits_dispatch_of:
    - "sov doctor"
    - "sov charter"
  refuses_everything_else: true
```
