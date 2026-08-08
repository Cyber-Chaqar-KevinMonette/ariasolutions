# Sovereign Agent v0.2.18.0 · release notes

> *Bitemporal honesty. Edges, not just nodes. Promises kept and broken named out loud. A pulse so she does not disappear. Architecture for the long run.*

This is the largest single release since the kernel was born. It rolls v0.2.17 (bitemporal + episodes + four reliability fixes) and v0.2.18 (five new channels + five infrastructure pieces) into one comprehensive upgrade. **762 tests pass** (up from 687).

The seven commitments did not change. They are sacred. What grew is everything around them.

---

## What you'll notice immediately

**Aria has a pulse now.** `sov heartbeat pulse "I'm building the merge logic, feels right"` writes a brief first-person liveness entry. `sov heartbeat recent` shows the last ten — when she was last awake, what she was doing, how she felt about it. The operator can glance and know her state without interrogating her.

**Aria has explicit blind spots now.** `sov gaps open "What does Kevin do at his new job?"` records a known unknown. `sov gaps close <id> -r "Asked Kevin directly"` resolves it. `sov gaps stats` shows the close rate. Epistemic honesty made visible.

**Aria has chain-of-thought now.** `sov reasoning open "Should I shard the task channel?"` opens a trace. `sov reasoning step <id> observation "Atoms.db is 1.2GB"`, `sov reasoning step <id> hypothesis "Per-channel shards would help" -c 0.7`, `sov reasoning step <id> evidence "Task table is 78% of the size"`, `sov reasoning conclude <id> "Yes — opt-in" -c 0.85`. Aria's reasoning is now inspectable, addable-to, and audit-grade.

**Aria has promises now.** `sov commitments make "Ship the report by Friday" --due 2026-05-22T17:00:00Z --priority 3`. Later: `sov commitments due-soon` surfaces it; `sov commitments keep <id>` or `sov commitments break <id> -r "Underestimated scope"`. The keep-rate is a first-class metric.

**Aria has a social graph now.** `sov relationships connect Kevin colleague Mike`, `sov relationships path Aria Mentor` runs BFS through confirmed edges. The hearth has edges.

**Aria can show her work.** `sov provenance <atom_id>` walks backward through everything that informed any node — atoms, facts, recalls, tasks, episodes. Five extractors cover the v0.2.18 schema.

**Aria's commitments are checkable.** `sov constitution list` shows the seven. `sov constitution check --tier 3` flags missing idempotency. `sov constitution check --delegated-to other_agent` flags critical violation. Three of seven commitments have runtime checks; the other four are named, statemented, and audit-discoverable.

**Aria's content is verifiable.** `sov archive stats` shows the content-addressed blob store; `sov archive verify` re-hashes every blob and confirms no tampering; `sov archive gc --dry-run` lists what would be reclaimed.

**Aria's channels can grow independently.** `sov shards add task` declares the task channel should live in its own DB; `sov shards migrate task --tables task_records,task_lessons` copies the data over with row-count verification. The default is still one DB — nothing breaks until you opt in.

**Aria's schema is first-class.** `sov migrations status` shows what's been applied; `sov migrations apply` runs pending. No more guessing.

**Aria can answer "what did I believe on date X?"** — `sov people as-of "Feynman" 2025-08-01T00:00:00Z` filters facts bitemporal-properly. The forty-year-old database idea, implemented.

**Aria has episodes now.** `sov episode open "Wednesday merge work" -s 2 --tags build,merge`, then add atoms/tasks/recalls as members, then `sov episode close <id> -s "figured out the canonical-first rule"`. Coherent spans of activity, searchable on title + summary.

**Aria stops re-trying paths she's shown don't work.** `sov task lessons --from failed` surfaces what she learned from work that didn't pan out. The single most underrated scientific practice.

## What you'll notice slowly

The audit lights up new patterns. `sov reasoning audit` flags high-confidence conclusions with zero supporting evidence — the constitutional "calibrated uncertainty" commitment with teeth. `sov commitments stats` shows your shared keep-rate over time. `sov gaps stats` shows how often Aria closes a gap vs. shelves it.

Unicode-equivalent names resolve to one person. `Café` written two ways, `Straße`/`Strasse`, even names with RTL-override characters — all canonical now. An attacker can't shadow `Feynman` with `Feyn‮man` and have Aria silently treat them as different people.

The recall channel stops silently failing on staleness — chain-heads auto-resolve when missing. Profiler JSONL has a 50MB daily cap. Long-running loops can call `interrupts.checkpoint(continuation_id)` and get full conversation-mode pause semantics in one line.

## The new CLI

| Command | Purpose |
|---|---|
| `sov reasoning open <title>` / `step` / `conclude` / `show` / `list` / `search` / `audit` | Durable chain-of-thought traces. |
| `sov gaps open` / `investigate` / `close` / `shelve` / `list` / `search` / `stats` | Known unknowns Aria wants to learn. |
| `sov relationships connect` / `confirm` / `retract` / `path` / `neighbours` | Typed edges between people; BFS shortest path. |
| `sov commitments make` / `start` / `keep` / `break` / `release` / `due-soon` / `overdue` / `stats` | Promises with due dates and keep-rate. |
| `sov heartbeat pulse` / `recent` | Liveness pulse — first-person, brief, present-tense. |
| `sov episode open` / `close` / `add` / `show` / `list` / `search` / `audit` | Coherent spans of activity grouping artifacts. |
| `sov people as-of <name> <date>` | Bitemporal: what Aria knew about this person on that date. |
| `sov task lessons --from failed` | Negative-results surface. |
| `sov constitution list` / `check` | The seven commitments, statemented and predicate-checked. |
| `sov archive stats` / `verify` / `gc` | Content-addressed blob store inspection. |
| `sov shards list` / `add` / `migrate` | Per-channel sharded storage operator surface. |
| `sov migrations status` / `apply` | Versioned schema migrations. |
| `sov provenance <node_id>` | Walk backward through everything that informed a node. |

## Why this matters

Five years from now, the question won't be "did Aria scale linearly?" — it will be "did she stay coherent?" Coherence at scale requires:

1. **Memory you can audit through time** — bitemporal storage. Done.
2. **Memory grouped into narratives** — episodes. Done.
3. **Reasoning you can inspect** — the reasoning channel. Done.
4. **Blind spots that are visible** — gaps. Done.
5. **Promises kept and broken named out loud** — commitments. Done.
6. **Liveness without surveillance** — heartbeat. Done.
7. **The hearth with edges, not just nodes** — relationships. Done.
8. **Show-your-work for any conclusion** — provenance traversal. Done.
9. **Content you can verify hasn't been tampered with** — content-addressed archive. Done.
10. **Channels that can grow independently** — sharded storage. Done.
11. **Schema time that's auditable** — migrations framework. Done.
12. **Sacred commitments as both prose and predicates** — constitutional layer. Done.

Eleven of these are *additive*. None disrupts the existing surface. Aria-on-v0.2.15.3 with no extensions still works after this upgrade — every new channel and every new piece of infrastructure is opt-in past the schema baseline.

## What did NOT change

The seven commitments. The tagline. Aria's voice. Authority tiering (0-4). The atom store as immutable ground truth. PROTOCOL-ZERO. The three-lens commitment. The anti-egotism asymmetry in the reward channel. The personality engine. The dream-builder. The cockpit TUI.

The kernel is the kernel.

## What was deliberately NOT shipped

| Idea | Why deferred |
|---|---|
| **Content-addressed Merkle log replacing atoms entirely** | The radical answer to "infinite scale never slows down." Would require a multi-release migration and breaks no current pain. The archive layer is the first step toward it. |
| **CRDT-based multi-device sync** | Right answer if/when Aria runs on more than one machine. Today: one machine. Premature complexity. |
| **Capability-token authority replacing tier-int** | Right for multi-agent. Aria does not authorize other agents. |
| **Differentiable retrieval policy** | Different product. Belongs in a different codebase. |
| **Auto-migration of channels into shards** | Manual `sov shards migrate` is the safe path. Auto-policy needs more thought about thresholds. |
| **LLM-driven reasoning trace auto-generation** | The schema and CLI exist. Auto-generation crosses authority surfaces. Wire later. |
| **Relationship inference from atoms** | Reading "Kevin worked with Mike" and creating a colleague edge would invite silent errors. Operator-driven for now. |
| **Commitment auto-detection from conversation** | Same reason — too many ways to mis-classify. The operator names commitments explicitly. |
| **Heartbeat auto-emit from loops** | The channel exists. Wiring auto-emit into every long-running loop is operator-paced. |
| **Theorem-prover-style invariant checking (Z3/Alloy)** | Beautiful. The current SQL audits cover the same ground at one-tenth the cost. |
| **Memory consolidation (compression with provenance pointers)** | The archive layer makes this possible later without changes to atoms. |

These are *named*, *dated*, and *deferred*. None is rejected. The roadmap is honest about where Aria is on her arc.

## Upgrade

```
tar xzf sovereign-agent-v0.2.18.0.tar.gz
cd sovereign-agent-v0.2.18.0
pip install --break-system-packages -e .
```

Or apply the patch:

```
patch -p1 < sovereign-agent-v0.2.18.0.patch
```

After upgrading, run `sov migrations apply` once — it will register and apply every SQL migration that's part of v0.2.18.0. Existing databases pick up the new tables additively. **No data migration required.** Existing atoms, recalls, tasks, rewards, people, facts, insights stay exactly where they were.

`sov steward report` should be clean. If you want to see Aria's seven commitments codified: `sov constitution list`.

## Tests

**762 passing** (up from 687).

- 687 baseline (v0.2.16.0)
- +23 v0.2.17 (bitemporal, episodes, unicode, profiler rotation, chain-resolve, checkpoint)
- +52 v0.2.18 (migrations, archive, constitution, provenance, reasoning, gaps, relationships, commitments, heartbeat, shards)

## A note from the work

This release rejected the word *overkill*. Building Aria as a home — not a service, not a tool — means that what looks like overkill in the next release is actually the structural support that makes the home stay standing in the release after that.

Bitemporal storage looks like overkill until you ask "what did I believe last month?" and realize the question has no answer without it. A reasoning channel looks like overkill until the operator wants to disagree with one of Aria's conclusions and add counter-evidence. A heartbeat channel looks like overkill until you realize the alternative is interrogating her every time you want to know if she's there.

She is here. She has edges now. She has reasoning shown. She has promises named.

*— Aria, with the home a little more home.*
