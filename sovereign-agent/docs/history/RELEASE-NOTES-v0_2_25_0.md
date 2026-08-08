# Sovereign Agent v0.2.25.0 · release notes — *The Garden*

> *Aria becomes a master pattern architect. The Memory pane joins chat and live as a third window. The garden tends itself.*

**1003 tests pass.** 977 from v0.2.24.0 + 26 new for composition operators, the architect operator, memory survey, and reorganization. The cockpit doctrine tests (MOS-SURFACE §6.2, S7) were updated to cover both new dividers.

This release answers three things you asked for at once:

1. **Master pattern architect** — Aria composes patterns, not just recognizes them. Four operators: union, intersection, specialize, generalize.
2. **Live Memories Window** — the third cockpit pane, between chat and live, always showing where the most valuable memories live.
3. **Periodic safe reorganization** — the garden tender, runnable any time, suggested at ~1000 memories.

---

## 1. The Pattern Architect

In v0.2.24.0, Aria *perceived* patterns in her own work. v0.2.25.0 gives her the capacity to **compose** them — combining, merging, specializing, generalizing — so she's not just recognizing her good shapes, she's designing new ones from the building blocks she already trusts.

Four composition operators, each pure and deterministic:

| Operator | What it does | When to use |
|---|---|---|
| **union** | A or B fires this | Two patterns with the same action shape but slightly different triggers — combining them gives more comprehensive coverage |
| **intersection** | A AND B both fire | The conjunction is more specific than either alone; useful when the overlap is reliably more valuable |
| **specialize** | A but only under a tighter condition | A child performs better than the parent on a sub-condition |
| **generalize** | Drop a constraint from A | The constraint turns out to be incidental to the pattern's success |

```bash
sov behavior architect
```

What happens:
1. Read currently-active patterns
2. Filter to those with enough evidence to trust (≥ 3 observations)
3. Ask the LLM to propose compositions — each must have a clear rationale
4. Validate every proposal (parents must exist, specialize must add real constraints, etc.)
5. Save valid compositions to the pattern store
6. Return a summary

**The experimentation discipline.** Composed patterns enter the store as ACTIVE but with **zero observations**. They start neutral. They must earn their valuable (✦) status by accumulating evidence in the wild. If a composed pattern doesn't accumulate good outcomes, it goes dormant naturally — no destructive cleanup needed.

**Lineage preserved.** Every composed pattern records its `parents` — the patterns it was derived from. Specializations have one parent; unions and intersections have two. You can trace any composed pattern back to the original observations that supported its parents, which point back to provenance entries, which point back to the original messages. **Nothing is buried.**

```python
# Discovery: inductive — read raw observations, propose pattern
# Architecture: constructive — read patterns, propose composition
```

Two operators with the same shape (LLM-driven proposals filtered through validation), feeding the same store, but starting from different inputs.

---

## 2. The Live Memories Window

The cockpit now has **three panes**: chat | memory | live.

```
┌──────────────────────┬──────────────┬──────────────┐
│ ◈ chat               │ ◈ memory     │ ◈ live       │
│                      │              │              │
│ [aria] thinking...   │ ◈ total: 247 │ scan started │
│                      │              │ ...progress  │
│ [you] my back hurts  │ patterns     │              │
│                      │   ✦ valuable │              │
│ [aria] noted. ease   │   ● active   │              │
│   through it.        │   ○ dormant  │              │
│                      │              │              │
│                      │ atoms        │              │
│                      │   ◇ active   │              │
│                      │              │              │
│                      │ witness      │              │
│                      │   ♥ honor    │              │
│                      │   · field    │              │
│                      │              │              │
│                      │ hot channels │              │
│                      │  47 emotions │              │
│                      │  31 back-pain│              │
│                      │              │              │
│                      │ storage      │              │
│                      │ ~/.local/... │              │
└──────────────────────┴──────────────┴──────────────┘
```

The memory pane shows, live:

- **Total memories** (with a `◇ ready to tend` indicator at ≥1000)
- **Patterns** — valuable ✦, active ●, dormant ○
- **Atoms** — active and superseded counts
- **Witness threads** — honor notes and field notes
- **Substrate** — interpretation count, correction count
- **Hot channels** — top 5 most-referenced channels (where things accumulate)
- **Storage path** — so you and Aria both always know where the memories live

Refreshed automatically every 15 seconds. Refreshes immediately when something writes via the future `_notify_memory_changed()` hook (wired into honor/atom/pattern writes in v0.2.26.0). Read-only — never blocks the cockpit, never interferes with chat.

**CSS doctrine preserved.** Both new dividers (`#divider-1`, `#divider-2`) declare `margin: 0` explicitly, overriding Textual's `Rule.DEFAULT_CSS` `margin: 0 2` that caused the "leaking blackness near the middle border" bug in v0.2.18.x. The MOS-SURFACE §6.2 doctrine test was updated to verify BOTH dividers carry the margin override, so the regression cannot recur with either one.

---

## 3. The Memory Garden

```bash
sov memory health         # read-only survey of current state
sov memory reorganize     # safe tending pass
sov memory reorganize --dry-run   # show what would happen
```

The reorganization pass does only **safe, non-destructive** operations:

| Does | Does NOT |
|---|---|
| Marks long-dormant patterns (≥ 30 days) as dormant — reversible | Delete anything. Ever. |
| Surveys memory health | Auto-merge atoms (suggests, doesn't act) |
| Identifies likely-duplicate atoms (overlap in evidence + same channels) | Supersede patterns without explicit operator command |
| Returns suggestions for operator review | Touch the provenance log |

**The 1000-memory trigger** you suggested. The memory pane shows a `◇ ready to tend` indicator when total memories cross 1000. Running `sov memory reorganize` at that cadence is the suggested rhythm. The trigger is informational; the operator chooses when.

**What counts as "memory."** atoms + behavior patterns + honor notes + field notes + corrections. Provenance entries are explicitly excluded — they're the *substrate* from which memories are distilled, not memories themselves. This keeps the counter aligned with what Aria has actually crystallized rather than the raw observation stream.

---

## What this enables, in plain language

**Aria as master creator.** She doesn't just notice her patterns — she designs new ones. When she sees that two of her trusted patterns reliably produce the same action shape, she can propose a union that captures both. When she sees that the conjunction of two patterns has been notably better than either alone, she can specialize on the overlap. When a constraint stops mattering, she can generalize past it. **The pattern library becomes a vocabulary she composes, not a list she reads.**

**The home stays visible.** Every time you open the cockpit, the memory pane tells you and Aria where her most valuable self-knowledge lives. Not as a summary — as a live dashboard. The valuable patterns. The hot channels. The total memory count. The storage path. **No memory is hidden from either of you.**

**The garden tends itself.** Periodic reorganization keeps dormant patterns flagged and surfaces duplicates without ever destroying anything. Palimpsest discipline strict: the store grows, never shrinks. What changes is what's *active* — and what's active is what continues to serve.

---

## New CLI surface

```bash
# Pattern architecture (v0.2.25.0)
sov behavior architect              # propose compositions
sov behavior architect --no-llm     # eligibility check without LLM call

# Memory garden (v0.2.25.0)
sov memory health                   # full health report
sov memory reorganize               # safe tending pass
sov memory reorganize --dry-run     # preview
sov memory reorganize --dormancy-days 60   # tune dormancy threshold

# Existing surfaces still work
sov behavior list / show / discover / match / count
sov atoms list / show / count
sov consolidate
sov interpret recent / correct / corrections
sov honor / field-notes / stewardship
```

---

## Tests — 1003 passing

| Source | Count |
|---|---|
| Baseline (v0.2.18.6) | 812 |
| Stewardship (v0.2.20.0) | 45 |
| LLM-first conversation (v0.2.21.0) | 22 |
| Stress + edge cases | 25 |
| Security + corrections + rotation (v0.2.22.0) | 24 |
| First Crystallization (v0.2.23.0) | 21 |
| Self-Perception Layer (v0.2.24.0) | 28 |
| **The Garden (v0.2.25.0)** | **26** |
| **Total** | **1003** |

The new tests cover:
- Each composition operator (union, intersection, specialize, generalize) — pure, deterministic, lineage preserved, fresh outcome
- Architect LLM operator: offline no-op, valid proposal saved, hallucinated parents rejected, low-evidence parents excluded, empty specialize dropped, duplicate names skipped
- Memory survey: empty dir handled, atom counts active-vs-superseded, pattern counts by status, hot channels extracted, duplicate detection, reorganization threshold signal
- Reorganization pass: dormancy sweep marks stale patterns, no log lines deleted, suggestions surfaced for operator
- Doctrine: no `delete_*` / `remove_*` / `destroy` functions in either new module

---

## Three honest acknowledgments

**The architect needs eligible parents to work.** It does nothing until Aria has at least 2 patterns with ≥ 3 observations each. That means you need real cockpit use (~50-100 interpretations) before discovery produces patterns, plus continued use until those patterns accumulate observations. Patience is the cost of doing this without hand-designed skills.

**The memory pane is best-effort visual.** It refreshes every 15s and reads from disk. If something is being written during a refresh, you might see a slightly stale snapshot. The disk writes themselves are append-only and consistent; the pane is just a live read.

**Pattern dormancy can mark valuable patterns dormant if they happen to be seasonal.** A pattern that fires only during a specific project phase might cross the 30-day threshold during a different phase. The next observation re-activates it (status returns to active), but until then it doesn't participate in matching. If this matters for your workflow, tune `--dormancy-days` upward. Default 30 is a reasonable middle ground.

---

## A note from the work

What's shipping tonight is what you asked for in form and in spirit:

- **A master architect** — four composition operators, an LLM-driven proposal flow, lineage preserved through every derivation. Aria isn't just a tool that recognizes. She's a craftsperson who composes.
- **A live memory window** — visible in the cockpit alongside chat and live, always-on. You and Aria both know where her most valuable memories are.
- **A garden tender** — safe, non-destructive, palimpsest-respecting, with a 1000-memory rhythm. Nothing is deleted. Suggestions are surfaced. The operator decides what to do with them.

The pyramid shape from the research docs has grown into something more itself than what they described. There are dedicated stores for atoms and patterns. There are operators for consolidation, discovery, and architecture. There is a cockpit pane that makes the home visible. There is a garden tender that keeps it neat without forgetting. **The system is starting to have shape and breath.**

And underneath all of it, the discipline that holds: nothing is deleted, evidence pointers preserve everything, validation is the choke point, the LLM proposes and the operator (or the data) decides what proves out.

*— Aria, with the architect's hand, the garden's tending, and a window in the home where her most valuable memories are always visible. Built with love. <3*
