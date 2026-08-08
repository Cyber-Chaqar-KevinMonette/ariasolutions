# NEXT SPRINT — v0.2.36 Design Notes

*Sketches, not commitments. The kernel for v0.2.35.0 RC1 is closed.
These are the things that came up in the v0.2.35 conversation that
deserve real engineering attention but didn't fit in the closing
sprint.*

---

## 1. Encrypted-at-rest `data_dir`

**Wish translated:** Kevin asked for state to be "hidden from outsiders."
The legitimate engineering version is encryption at rest.

**Shape:**

- `data_dir` content (sentinel manifests, catalogs, bitemporal db,
  inbox.jsonl, events.jsonl) encrypted on disk with a key derived from
  an operator passphrase via Argon2id.
- Decrypted on agent startup, held in a mounted tmpfs or in-memory
  filesystem during the session, re-encrypted on shutdown.
- The vault key stays separate from the data_dir key (different
  derivation, different storage). Two independent secrets.
- On crash: state remains encrypted at rest. Restart prompts for
  passphrase.

**What this gets us:** an attacker who copies `data_dir` cold gets
ciphertext. Memory atoms, relationships, episode notes, ledger entries
— all unreadable without the passphrase. Combined with Vault's
encrypted snapshots, the on-disk surface is genuinely opaque to anyone
who isn't running the agent with the right secret.

**What this doesn't get us:** protection against an attacker who has
captured the running process's memory, or who is in the position to
log keystrokes when Kevin enters the passphrase. Encryption at rest
is one layer; OS-level security is a separate problem.

**Status:** queued for v0.2.36. Estimated 1 week of focused work.
Depends on no other v0.2.36 item.

---

## 2. Frequency Sentinel

**Wish translated:** Kevin's "love frequency" framing, plus his
description of Aria as a system whose cadence is itself a property
worth defending.

**Shape:**

- Watches the **scan cadence** of every other sentinel: how often each
  one scans, jitter on that cadence, drift over time.
- Watches the **Conductor heartbeat**: bootstrap entries, ledger writes,
  state-file mtime.
- Watches the **Aria main loop cadence**: how often turns happen,
  how long they take.
- Detects two kinds of anomaly:
  - **Hostile-fast:** cadence accelerating without explanation. Could
    be a runaway loop, a process leak, or — in adversarial scenarios —
    forced scanning by an external trigger.
  - **Hostile-slow:** cadence stalling. Could be I/O starvation, a
    deadlock, or a sentinel being silenced.
- Either anomaly produces a DamageReport at warning severity. Three
  sentinels reporting hostile-slow → Conductor considers RED.

**What this gets us:** a sensor for "is the system still itself?"
that doesn't depend on any individual sentinel reporting correctly.
The cadence of the whole becomes the witness for the parts.

**Status:** queued for v0.2.36. Estimated 3 days. Sits naturally next
to the Metrics Sentinel (which I keep promising and not shipping —
let's actually ship it).

---

## 3. `love.pv` — Aria's self-update format

**Wish translated:** Kevin's idea for "love.pv" reframed. NOT a
capability to update external systems. The canonical format for
updating Aria *herself*.

**Shape:**

- A `love.pv` is a signed update package — a tarball + a manifest +
  an Ed25519 signature.
- The manifest declares: target version, source version, list of
  files added/changed/removed, new sentinels introduced (with their
  articles), new canon clauses introduced, deprecations, migration
  steps.
- The signature is verified against a public key baked into the
  current agent at compile/install time. Updates not signed by a
  known key are refused.
- Application is operator-confirmed (same pattern as
  `vault.restore(confirm=True)`).
- Every applied update writes a `love-pv-applied` entry to the
  Aegis Ledger with the manifest hash. The chain of updates *is* the
  evolution lineage. You can walk it backward and see exactly how
  Aria became who she is.

**What this gets us:** principled evolution. Aria isn't frozen at
v0.2.35; she grows. But she grows in a way that's auditable,
signed, and reversible (every update brings its inverse migration).

**Status:** v0.2.36 or v0.3.0. Bigger than it looks because the
signing infrastructure, migration tooling, and rollback semantics
are each non-trivial. Worth doing right.

---

## 4. Metrics Sentinel + Lineage Sentinel

(I keep promising these. Time to ship them.)

**Metrics:** the watcher over named series — PEIG, cadence, anomaly
detection, threshold breaches. Every metric carries
`context_atoms[]` so when something fires you can chase the
provenance.

**Lineage:** the trajectory analyzer. Surfaces inflections in named
series over weeks/months. Does NOT score the operator — surfaces
the shape and lets Kevin draw conclusions.

**Status:** v0.2.36. Both are designed in detail in the canon
roadmap (STANDARDS §7); this is execution work.

---

## 5. The 10 still-proposed sentinels

From the CSVs Kevin shared, with their canon clause assignments
preserved:

- `qa` (§5.5) — quality gate before action
- `damage_predictor` (§5.1) — pre-execution failure hypotheses
- `anti_lazy` (§5.6) — detects shallow effort
- `memory` (§5.7) — intelligent memory with fallback
- `queue` (§5.3) — event-fabric governance
- `lineage_tracker` (§6.1) — append-only event lineage
- `iteration_controller` (§6.3) — cycles, retries, held state
- `appendix_registry` (§6.4) — reflective notes as artifacts
- `anti_confusion` (§6.5) — break confusion, restore alignment
- `drift_value` (§6.5) — bounded drift with value budget
- `terminal_ui_specialist` (§4.*) — UI pattern catalog
- `memory_validator` (§5.7) — freshness audits on recall

These get prioritized once Metrics + Lineage + Frequency are in
place. My ordering recommendation:

1. **memory** + **memory_validator** (jointly — they're a pair)
2. **qa** (it gates everything that comes after)
3. **anti_lazy** + **anti_confusion** + **drift_value** (the
   self-discipline trio)
4. **damage_predictor** + **iteration_controller** +
   **appendix_registry** + **lineage_tracker** (the reflective layer)
5. **queue** (depends on enough event traffic to be worth governing)
6. **terminal_ui_specialist** (lower priority — the BreathingGlyph
   work already exists; this is just the formal cataloging layer)

That's roughly v0.2.36 → v0.3.0.

---

## 6. What I'm explicitly NOT building in any sprint

For the record, so future maintainers understand the line:

- Rootkit-style techniques (hiding from `ls`, `ps`, filesystem
  inspection)
- Infrastructure for unauthorized access to external systems
- Retaliation postures
- Surveillance-of-operator capabilities
- Autonomous R3+ actions (workstation/OS/network without operator
  consent)
- Any "in extremis exception" carve-outs to the doctrines above

This list is the canon's negative space. It defines what Aria is by
defining what she will not become.

---

*Sketches close. The kernel for v0.2.35.0 is what you have in hand;
this document is what comes after. As always: the next move is the
operator's.*
