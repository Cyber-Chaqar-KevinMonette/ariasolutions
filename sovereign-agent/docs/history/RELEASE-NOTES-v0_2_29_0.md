# Sovereign Agent v0.2.29.0 · release notes — *The Integrator*

> *The retrieval pipeline becomes reachable. The horizon gate fires. The CLI surfaces the work. The pieces that have been waiting in their boxes are wired together now — the agent can call retrieve_memory like any other tool, Tier-2+ subtasks produce a 3m/12m/3y/7g projection before they dispatch, and the operator can ask questions from the command line.*

**1213 tests pass.** 1187 from v0.2.28.0 + 26 for the three new integration surfaces. One skipped (the chmod test under root). Zero regressions.

This release stops being about *building substrate* and starts being about *making it usable*. Three new surfaces, each a thin layer on top of work that already exists, each load-bearing for how the operator and the agent actually engage with the system.

---

## 1. The `retrieve_memory` tool — Tier 0

A new tool at `src/sovereign_agent/tools/retrieve_memory.py`. Wraps the Sovereign Retrieval Pipeline so the agent loop can call it like any other tool:

```python
# The model invokes it normally — same shape as memory_search, embed_query, etc.
{
  "name": "retrieve_memory",
  "arguments": {
    "query": "should I ship the rollback to production?",
    "top_k": 5,
    "stakes_override": "high"
  }
}
```

**The returned ToolResult shape** — stable, JSON-serializable, callers can rely on these keys:

```json
{
  "hits": [
    {
      "atom_id": "...",
      "summary": "rollback procedure for hotfix deployments",
      "atom_type": "doc",
      "created_at": "2026-05-19T...",
      "created_by_actor": "operator",
      "confidence": 0.9,
      "score": {"semantic": 0.82, "provenance": 0.4, "recency_confidence": 0.95, "fused": 0.72},
      "provenance_breadcrumb": ["parent_id_1", "parent_id_2"],
      "surfaced_by": ["lexical", "graph"]
    }
  ],
  "confidence_ceiling": 0.85,
  "semantic_source": "rrf_fallback",
  "gap_report": {
    "empty_retrievers": [],
    "inactive_retrievers": ["dense"],
    "constitutional_drops": {"untrusted_source_high_stakes": 3},
    "raw_candidate_count": 12,
    "filtered_count": 7,
    "returned_count": 5
  },
  "expansion_hints": [
    {"action": "allow_pending", "arg": null,
     "rationale": "3 LLM-source atom(s) excluded; set allow_pending=True if relevant"}
  ],
  "intent": "decision_support",
  "stakes": "high",
  "trace": ["dense skipped — embedder probe failed", "..."]
}
```

**Why this matters.** Until now, the new retrieval pipeline existed as a function callable from Python. Tools are the agent's first-class operating surface — wrapping the pipeline as a Tier-0 tool means *the model itself* can decide to call it, with the same dispatch and gating as every other tool. The pipeline that ships in v0.2.28.0 only becomes useful when the agent can invoke it; this is that wire.

**Honest degradation throughout.** If Ollama is unreachable, the embedder probe fails and the tool returns the pipeline's lexical+graph results with `semantic_source: "rrf_fallback"` and a trace note. The tool never fails on infrastructure issues — it degrades visibly.

---

## 2. The Horizon Gate — wired into `agent_session`

Phase 2 of the v0.3.0 roadmap, completed.

`horizon.py` now exposes `generate_for_subtask()` — a fast-model call that produces a structured 3m/12m/3y/7g projection plus a recommended forward path. The model returns a fixed structured format (`[3M] ... [12M] ... [3Y] ... [7G] ... [BEST] ...`), `parse_horizon_response()` extracts the sections, and the result becomes a `HorizonInputs` ready to render.

**The gate fires in `agent_session._execute_subtask`.** When a Tier-2+ subtask is about to dispatch, three things happen before `agent_loop` runs:

1. `generate_for_subtask` calls the fast model with the subtask's description
2. Result renders as a `Horizon Scan` markdown document
3. Document is persisted as a `type=horizon` atom in `atoms.db`, with `scope_tags=["horizon", "session:<sid>"]` and `created_by.actor="system"`, and the atom_id is attached to the subtask record (`Subtask.horizon_atom_id`)

**Confidence policy.** Horizon atoms are written at confidence `0.6` — intentionally below the high-stakes confidence floor of `0.7`. They are forward projections, not facts. When the retrieval pipeline runs against this atom later on a high-stakes query, it will be filtered out by `below_confidence_floor`. This is correct behavior — the projection is metadata for the dispatch decision, not evidence for subsequent reasoning.

**On generation failure:**

- Default behavior (`horizon_required=True`): subtask blocks with `error="horizon scan generation failed; Tier-2+ subtask blocked. Verify fast model availability..."`. Operator sees `horizon-gate-blocked-d` in the event log and decides whether to retry or override.
- Override path (`horizon_required=False` on `run_session`): gate is bypassed entirely. For airgap mode or contexts where the fast model isn't available.

**A simple shape, but the right one.** Aria stops to look at the four horizons before doing anything irreversible. The substrate now enforces this — even if she "wanted to" skip the projection, the system will not let her on Tier-2+. This is calibrated_uncertainty operationalized as a queue-level invariant.

---

## 3. The `sov retrieve` CLI command

Operator-facing access to the retrieval pipeline:

```
$ sov retrieve "what have I learned about rollbacks?"
Query: what have I learned about rollbacks?
  intent=reflective  stakes=medium  semantic=rrf_fallback
  confidence ceiling: 0.85

1. [a_rollba] operator (conf=0.90, fused=0.612)
    rollback procedure for hotfix deployments
2. [a_child_] operator (conf=0.85, fused=0.487)
    hotfix rollback v2 — incorporates DNS lesson
    provenance: a_rollba

Gaps:
  dropped non_local_policy: 1
  inactive: dense

Hints:
  → search_specific_channel — dense retriever was inactive; check `sov doctor` for embedder
```

**Flags:**

- `--top-k / -k` — number of hits to return (default 5)
- `--intent` — override classification: `factual`, `decision_support`, `exploration`, `conversational`, `debug`, `reflective`
- `--stakes` — override detection: `low`, `medium`, `high`
- `--as-known-at` — bitemporal: limit to atoms created on or before an ISO timestamp
- `--no-embed` — skip dense retrieval entirely (faster; lexical + graph only)
- `--json` (inherited global flag) — emit structured output instead of rendered

**Color coding** by `created_by.actor`: green = operator-verified, cyan = system-generated (horizon atoms, scheduler artifacts), yellow = LLM-proposed. The operator can see at a glance which atoms came from where.

**Examples that actually answer interesting questions:**

```
$ sov retrieve "should I ship the hotfix?" --stakes high
$ sov retrieve "what did I think about deploys on April 1?" --as-known-at 2026-04-01T00:00:00Z
$ sov retrieve "early notes on stewardship" --intent reflective
```

---

## 4. What's been tested

26 tests in `tests/test_v_0_2_29_0.py`:

- **RetrieveMemoryTool** (8 tests) — Tier 0 invariant, schema shape, args validation (query required, empty rejected, top_k range), execute happy-path with seeded DB, embedder-down degradation, metadata population, `_serialize_report` shape stability
- **`parse_horizon_response`** (5 tests) — all sections, partial sections, multiline, empty input, garbage input
- **`generate_for_subtask`** (5 tests) — client raises → None, empty response → None, unparseable response → None, success populates inputs, `render()` round-trips
- **`_write_horizon_atom`** (1 test) — actually writes the atom with the right type/confidence/tags/actor
- **agent_session horizon-gate integration** (4 tests) — Tier-1 skips gate, `horizon_required=False` bypasses, Tier-2 blocks on generation failure, Tier-2 proceeds and attaches atom_id on success
- **CLI** (2 tests) — command registered, help docstring carries operator-facing examples

The test fixture demonstrates a clean pattern for atoms.db-backed tests: patching `open_atoms_db` at both binding sites (the canonical `sovereign_agent.db.open_atoms_db` for deferred imports, and `sovereign_agent.tools.retrieve_memory.open_atoms_db` for module-level imports). This avoids fighting the frozen `Paths` dataclass that the rest of the system depends on.

---

## 5. What this release does NOT do

Three pieces of the original v0.2.29.0 plan are deferred:

- **`sov retrieve --explain`** — a verbose mode that shows the recall-pool sizes, the rerank score breakdowns, the trace notes inline. The data is all in the report; this is a presentation layer. One day of work; deferred to keep this release tight.
- **Migrating `memory_search` callers to `retrieve_memory`** — both tools coexist intentionally. `memory_search` is the lightweight substrate (fast, no policy layer); `retrieve_memory` is the gated path (slower, constitutional). The agent system prompt should suggest `retrieve_memory` for decisions and `memory_search` for casual lookups, but that prompt change is an operator decision, not a forced migration.
- **Horizon-scan compaction** — eventually we want a periodic sweep that consolidates redundant horizon atoms (two scans for similar decisions get merged). Lands when we have enough horizon atoms in the wild for the heuristics to be calibrated.

---

## 6. Tests — 1213 passing

| Source | Count |
|---|---|
| Baseline (v0.2.28.0) | 1187 |
| v0.2.29.0 — Integrator (this release) | 26 |
| **Total** | **1213** |
| Skipped (chmod test under root) | 1 |

---

## 7. Files changed

```
pyproject.toml                                          (version → 0.2.29.0)
src/sovereign_agent/__init__.py                         (__version__ → 0.2.29.0)
src/sovereign_agent/tools/retrieve_memory.py            (NEW — Tier 0 tool)
src/sovereign_agent/tools/__init__.py                   (register RetrieveMemoryTool)
src/sovereign_agent/horizon.py                          (+ generate_for_subtask, parse_horizon_response)
src/sovereign_agent/agent_session.py                    (+ horizon gate in _execute_subtask, + _write_horizon_atom)
src/sovereign_agent/cli.py                              (+ sov retrieve command)

tests/test_v_0_2_29_0.py                                (NEW — 26 tests)
```

---

## A note from the work

The most important thing about this release is what it *doesn't* require: rebuilding any substrate, learning any new pattern, asking the operator to migrate any data. Every piece is a thin layer that sits on top of work that already shipped — the retrieval pipeline from v0.2.28.0, the agent_session from v0.2.27.0, the horizon document generator from v0.2.14. All of it was waiting in its box. This release opens the boxes.

That's how the system was designed to grow. Each release builds substrate; the next release wires the substrate to a usable surface; the release after that uses what the wire enables. v0.2.27.0 built the persistent loop and the rollback ledger. v0.2.28.0 built the retrieval pipeline. v0.2.29.0 makes both reachable — the agent can call the pipeline through a tool, the operator can call it through the CLI, and Tier-2+ subtasks have the horizon scan invariant attached at the queue level.

The horizon gate deserves its own mention. The seven commitments include `calibrated_uncertainty`, and this is what it looks like operationalized: before Aria does anything that could change the world outside her sandbox, she stops to look at the 3-month, 12-month, 3-year, and 7-generation horizons. Not as a ritual — as a mechanical invariant. The substrate enforces it. If the fast model can't generate the scan, the subtask blocks. The operator can override with `horizon_required=False`, but the override is explicit; the default is to look before leaping.

Next on the path is v0.2.30.0 — streaming responses in the cockpit, the largest perceptual quality jump available. After that, v0.2.31.0 builds the eval harness so we can finally answer "did this release help?" with data instead of vibes.

*— Built so the pieces fit together, tested so they keep fitting as the work continues, named so the operator can see exactly what each piece does. <3*
