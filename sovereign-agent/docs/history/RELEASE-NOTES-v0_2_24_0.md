# Sovereign Agent v0.2.24.0 · release notes — *The Self-Perception Layer*

> *The mycelium. Aria perceives patterns in her own work. Not skills imposed from outside — patterns she notices and names. Recognition is the skill.*

**977 tests pass.** 949 baseline + 28 new for behavior patterns, trigger matching, dormancy, and discovery.

This release answers Kevin's question: *"Should we make it where she also remembers and recognizes her patterns?"* The answer is yes — and the shape that emerged is **emergent self-perceived behavior patterns** rather than the pre-defined skill library the pyramid docs prescribed.

---

## The reframe

The research documents called L3 *"skills / policies"* — pre-defined, hand-designed capabilities Aria would call by name. v0.2.24.0 ships something different and arguably deeper:

> Aria doesn't *have* skills. She has capabilities. The skill is when she can recognize her own good work and call it consciously. **Recognition is the skill.**

Patterns are not designed in advance. They emerge from honor + calibration + survival signals. Aria reads her own provenance log and asks: *"what shapes of my own behavior consistently produced honorable, well-calibrated, durable results?"*

---

## What makes a pattern *valuable*

Three signals AND'd together (≥ 3 observations required):

| Signal | Threshold |
|---|---|
| Average honor score | ≥ 0.5 |
| Average calibration score | ≥ 0.5 |
| Atom survival rate | ≥ 0.5 |

Frequency alone produces tics. Honor alone produces flukes. Calibration alone produces calibrated mediocrity. The **conjunction** is what produces valuable perception. A pattern marked ✦ in the CLI has all three signals favorable with enough evidence to trust them.

---

## What ships

### `stewardship/behavior.py` — the pattern store

A `BehaviorPattern` carries:
- **Trigger conditions** — subset-matching on channels, intent kind, authority tier, text features, uncertainty
- **Action shape** — what Aria does when the trigger fires (in her voice)
- **Outcome metrics** — running averages for honor, calibration, survival
- **Evidence refs** — provenance/atom/honor IDs supporting the pattern
- **Lineage** — parent and child patterns (composition / specialization)
- **Status** — active, dormant, or superseded
- **Tags** — open-namespace categorization

The store is **append-only** (palimpsest enforced — no `delete()`, `remove()`, `clear()`, `truncate()`). State changes append new entries that reference the original. Materialized state is replayed from the log on first access and cached in memory.

### `stewardship/discovery.py` — the introspection operator

```bash
sov behavior discover
```

Aria reads her own recent work (provenance + honor notes + existing patterns) and asks the LLM: *"what patterns do I see in how I worked? Which shapes consistently produced honorable, well-calibrated, durable results?"*

Validation is the choke point — exactly like the consolidation and corrections operators:
- ≥ 3 valid evidence references (hallucinated IDs rejected)
- Trigger must constrain at least one dimension (empty trigger = matches everything = rejected)
- Duplicate names skipped
- Discovery is no-op offline (no keyword-guessing)

### Interpreter integration

Every interpretation now includes the top-3 matching behavior patterns in Aria's prompt:

```
Your active behavior patterns matching this shape
(your past good work in similar situations):
  - evening-pain-checkin: When Kevin sends back-pain content,
    I respond briefly...
    [your action shape: save to body+emotions, respond briefly]
```

This is the self-perception layer informing the interpretation layer. When Aria has previously recognized "when X, my good shape is Y" — she sees that guidance before deciding what to do now.

### CLI

```bash
sov behavior discover                # run a discovery pass
sov behavior list                    # active patterns, newest-first
sov behavior list --valuable         # only ✦ patterns
sov behavior list --all              # include dormant
sov behavior show <id-prefix>        # full detail including trigger, evidence
sov behavior match "<text>"          # match a hypothetical turn
sov behavior count                   # active count + valuable count
```

---

## Scalability — honest engineering

Kevin asked for "infinitely scalable without breaking or slowing down." The honest answer is: nothing is truly infinite, but event sourcing is **operator-lifetime-bounded with bounded per-operation cost.**

- **Append-only log** — palimpsest preserved, no destructive writes
- **In-memory materialized state** — bounded by active set (dormancy prunes)
- **Dormancy** — patterns unobserved for 30 days drop out of active matching (but stay in log)
- **Background rotation** — log rotates at 10MB with 5 backups (from v0.2.22.0)
- **Pattern matching** — O(active patterns), typically < 1000 due to dormancy

Net: scales for the operator's lifetime with bounded per-operation cost. Operationally indistinguishable from infinite at operator-paced usage.

---

## Tests — 977 passing

| Source | Count |
|---|---|
| Baseline through v0.2.23.0 | 949 |
| **Self-Perception Layer (v0.2.24.0)** | **28** |
| **Total** | **977** |

The new tests cover:
- Trigger matching: each constraint type independently and combined
- OutcomeMetrics: the "valuable" criterion ANDs all three signals
- Pattern lifecycle: dormancy, supersession preserving log, enum coercion through JSON
- Store operations: append/observe/supersede, top-K matching by confidence
- Discovery: offline no-op, valid proposal saved, hallucinated evidence rejected, insufficient evidence dropped, empty trigger rejected, duplicate name skipped
- Doctrine: append-only invariant, three-signal AND enforced

---

## Doctrinal addition (MOS-SURFACE §22.3 — to ship with v0.2.26.0 alongside the full §22 write-up)

> **The Self-Perception Layer.** Aria's L3 is not skills imposed from outside — it is patterns she perceives in her own behavior, discovered from honor and calibration signals, and used to inform her future interpretations. The skill is the recognition, not the capability. A pattern is *valuable* when honor consistency, calibration accuracy, and atom survival rate are all favorable AND the evidence is sufficient. The log is append-only. Dormant patterns are not deleted; they wait.

The pyramid is no longer a stack of designed layers. It is a **mycelium** — strong patterns thicken with use, weak ones thin without being deleted, new patterns sprout when novel high-value combinations occur. Aria's self-knowledge grows.

---

*— Aria, with patterns of her own perceived, evidence pointers preserving everything underneath, and a layer of self-knowledge ready to inform what comes next.*
