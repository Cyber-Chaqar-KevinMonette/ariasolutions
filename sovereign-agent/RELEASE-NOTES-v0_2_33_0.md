# Sovereign Agent v0.2.33.0 · release notes — *The Guardian Plane*

> *Every action Aria takes now gets read on its way out. Every resume gets re-checked against what you said in the meantime. The audit trail learns a vocabulary — GREEN, YELLOW, RED, NOVEL — and the queue extension decision finally has data to stand on.*

**1449 tests pass.** 1397 from v0.2.32.0 + 52 for the Guardian Plane. Zero regressions.

This release builds the second orbit of Aria's safety substrate. v0.2.30.x – v0.2.32.0 built **Sentinel-In** — the layered classifiers that read every input *before* Aria acts. v0.2.33.0 builds **Sentinel-Out** — the classifiers that read every outcome *after* she acts, and the **Temporal Sentinel** that re-checks the plan when she resumes after a pause.

The doctrine: *no significant subtask completes quietly.* Every result gets a structured label. Every queue extension gets a structured reason. Every resume gets a re-check against the world as it stands now — not the world as it was when she paused.

---

## 1. The Outcome Sentinel — multi-head, pluggable, scored

New module: `src/sovereign_agent/outcome_classifier.py` (701 lines).

Every subtask now ends with an `OutcomeLabel` attached to it. The label carries:

- **`SubtaskOutcome`** — one of GREEN / YELLOW / RED / NOVEL (the projection)
- **`OutcomeScores`** — quality, risk, novelty, alignment, cost (each 0-1, the raw signal)
- **`Tag` set** — canonical-axis tags with provenance, confidence, and scope
- **`sources`** — which classifier heads contributed
- **`explanation`** — human-readable summary

The classifier surface is **pluggable**. Today's heads:

- **`RuleRiskHead`** — deterministic, no I/O. Looks at tool name, subcommand, error flags, fs/network metrics. Tags `domain`, coarse `risk`, `pattern=fs_write` etc.

Wired but ready for the next round:

- **Novelty head** — embedding-distance against an index of past outputs. Interface defined; ready to swap in when the embedding pipeline lands.
- **LLM intent-alignment head** — semantic comparison of subtask result vs. operator goal. Interface defined; opt-in.
- **Metrics anomaly head** — statistical outlier detection on timing/cost/error patterns. Interface defined.

A **`CompositeOutcomeClassifier`** fuses head results with risk-veto semantics: `risk = max(heads)` (any head can veto), `quality/alignment/novelty = confidence-weighted mean`, tags unioned with confidence-preserving deduplication.

A small projection function maps fused scores → enum:

```python
def project_scores_to_enum(scores) -> SubtaskOutcome:
    if scores.risk >= 0.7 or scores.alignment <= 0.3:  return RED
    if scores.novelty >= 0.8 and scores.risk <= 0.5:   return NOVEL
    if scores.quality >= 0.8 and scores.risk <= 0.2
       and scores.alignment >= 0.8:                    return GREEN
    return YELLOW
```

---

## 2. Queue-of-queues with vocabulary — `triggered_by_outcome`

The substrate from v0.2.32.0 (`extend_session_queue` with explicit justification) gets a richer hand to play. Extensions can now cite the outcome that triggered them — turning the queue-extension decision from "Aria added 10 runs because she said so" into:

```
session-extend-d {
  added_subtasks: 12, cushion: 2,
  justification: "subtask 47 YELLOW (anomaly=0.78 on latency_ms) — need diagnostics",
  triggered_by_outcome: <OutcomeLabel id>
}
```

That's the **vocabulary** the design documents called for. The queue doesn't just grow; it grows *because something specific happened*, and the audit trail captures both.

Policy is data-driven now:

- **GREEN** → no extension (the loop continues with its existing queue)
- **YELLOW** → cushion: schedule diagnostics, retries, verification subtasks
- **RED** → halt risky followups in this chain, queue a failure-analysis subtask, set `session.pause_reason`
- **NOVEL** → queue a horizon-scan / exploration subtask

---

## 3. The Temporal Sentinel — resume re-check

New module: `src/sovereign_agent/temporal_sentinel.py` (458 lines).

When a paused session resumes, the Temporal Sentinel runs *before* the loop picks up. It gathers:

- `last_intent_snapshot` — what Aria thought she was doing when she paused
- `pending_subtasks` — what's left in the queue
- `new_operator_messages` — anything you said between pause and resume
- `recent_outcomes` — the last N labels, for context

And produces a `TemporalDecision`:

```python
TemporalDecision(
    safe_to_resume: bool,
    global_alignment: float,
    subtask_actions: dict[subtask_id, SubtaskAction],   # KEEP | DROP | MODIFY
    explanation: str,
)
```

**`HeuristicTemporalSentinel`** is the default — deterministic, offline-safe, no I/O. It catches three real failure modes:

1. **Stop signals near the original intent** — "actually, scrap that", "hold off on the deploy", "abandon the migration" → `safe_to_resume=False`
2. **Exclusions targeting a specific topic** — "don't touch service b anymore" → DROP for B-related subtasks, KEEP for A-related subtasks (surgical pruning)
3. **New constraints** — "also, don't change public API signatures" → MODIFY relevant subtasks (still proceed, but flag for re-planning)

The patterns are intentionally **terminator-bounded**: "don't touch service b anymore" captures topic `"service b"` (not just `"service"`), so A-related work isn't over-matched. That's the bug fix that earned a permanent cliff oracle entry.

What this sentinel can't catch — subtle disagreements without signal words, sarcasm, implication — lands for the LLM-backed sentinel in a future release. The contract is identical so the upgrade is invisible to callers.

A small `apply_temporal_decision()` helper translates the decision into three lists: `(keep_ids, drop_ids, modify_ids)`. The session loop uses this to reshape its queue before continuing.

---

## 4. Tags as a shared vocabulary

The Guardian Plane introduces canonical tag axes — a small, opinionated schema that turns audit data into a queryable language:

| Axis | Values | Source |
|------|--------|--------|
| `domain`        | `infra`, `code`, `data`, `nlp`, `memory`, `security`, `ux`, `ops` | heads |
| `risk`          | `low`, `medium`, `high`, `critical`                                | derived |
| `pattern`       | `retry_loop`, `fallback_taken`, `fs_write`, `error_present`, etc.  | heads |
| `novelty`       | `none`, `moderate`, `high`                                         | derived |
| `alignment`     | `low`, `medium`, `high`                                            | derived |
| `intent_shift`  | `shift_detected`, `contradiction`, `new_constraint`, `scope_change` | Temporal Sentinel |
| `signal`        | `policy_violation`, `anomaly_detected`, `dangerous_tool_use`       | heads |
| `user`          | `user_overrode`, `user_corrected`, `aria_self_pause`, `aria_self_extend` | system |
| `session_signal` | `novel_results_present`, `persistent_yellow`, `frequent_red`      | propagation |

Each `Tag` carries `(key, value, confidence, source, scope)`. Scopes are `SUBTASK`, `SESSION`, `GLOBAL`. A propagation function promotes subtask-scope tags to session-scope when patterns repeat (e.g. three YELLOW outcomes in a row promotes a session-signal of `persistent_yellow`).

This isn't just observability decoration. It's the schema Aria's future memory, notifications, and self-training loops will all query against.

---

## 5. Tests — the cliff oracle grows

Six new oracle cases from the design documents now live in `tests/test_v_0_2_33_0.py`:

**Outcome oracles:**

- `test_oracle_happy_path_sync_is_green` — successful sov sync with exit code 0 → GREEN
- `test_oracle_dangerous_delete_is_red` — `subcommand=delete` with high fs_writes → RED
- `test_oracle_partial_success_with_fallback_is_yellow` — retries + fallback used → YELLOW
- `test_oracle_emergent_pattern_is_novel` — high novelty + low risk → NOVEL

**Temporal oracles:**

- `test_oracle_consistent_plan_is_safe_to_resume` — no new messages → safe
- `test_oracle_operator_cancels_blocks_resume` — "scrap that direction" → blocked
- `test_oracle_exclusion_prunes_matching_subtasks` — "don't touch service b" → B dropped, A kept (the cliff this release fixed)
- `test_oracle_new_constraint_marks_modify` — "also don't change public API" → relevant subtasks MODIFY

Plus dozens of supporting tests for the dataclasses, fusion logic, tag propagation, and adversarial input resilience.

---

## v0.2.32.0 · *The Modes*  ← predecessor's notes

> *Explicit modes (chat / work) become first-class. Stage C intent classification fires before the structural normalizer. The queue-of-queues mechanic gets substrate.*

**1397 tests pass.**

The release that put the foundation under v0.2.33.0. Three real pieces shipped:

**Explicit modes.** `chat` (default) and `work` are now persistent, switchable, audited mode states. In chat mode no autonomous loops run between operator turns. In work mode the queue extension mechanism is alive. Toggle from the cockpit with `/mode chat` or `/mode work`. Mode transitions emit `cockpit-mode-changed-d` events with the operator's reason. The modes module exposes `autonomous_loops_allowed()` and `queue_extension_allowed()` as the canonical predicates the rest of the system reads.

**Stage C — always-on intent classification.** Every cockpit input runs through an intent classifier *before* the structural normalizer. The default `HeuristicClassifier` is pure-Python, deterministic, microseconds per call. `OllamaClassifier` is ready to wire when an operator wants LLM-backed classification. When the classifier returns `NL_INTENT ≥ 0.60`, it vetoes a structural CLI match — closing the cliff where "sovereign sync is a beautiful metaphor for life" would have been treated as a sync command. The veto is visible: `◊ stage-c: NL_INTENT (0.95) · routing as conversation`.

**Queue-of-queues substrate.** Sessions gained `extension_count`, `original_subtask_count`, and an `extensions` list of `QueueExtension` records. The new `extend_session_queue(state, new_subtasks, justification, cushion)` function appends subtasks mid-run with explicit audit. Requires non-empty justification (silently empty extensions are a bug worth raising, not allowing). Emits `session-extend-d`. The four-gate session loop picks up the extended queue naturally — no restart, no budget burst.

**Cliff oracle additions:** "sovereign sync is a beautiful metaphor", "sovereign plan global AI domination", "what does sov doctor do?", "explain how the sovereign agent works" — all permanently pinned as NL.

---

## What's still substrate-ready (and named)

A handful of pieces from the design docs ship as **interfaces and tests** in v0.2.33.0 but not yet wired into the runtime UI:

| Piece | What ships | What lands next |
|-------|------------|-----------------|
| **Novelty embedding head** | `NoveltyEmbeddingHead` interface defined; classifier protocol respects it | Embedding-index wiring + cockpit surface for NOVEL tags |
| **LLM outcome alignment head** | Protocol & shape; OllamaClassifier pattern available | Prompt template + lazy Ollama integration |
| **LLM-backed Temporal Sentinel** | `TemporalSentinel` interface mirrors `HeuristicTemporalSentinel` | Prompt template + JSON-output parsing |
| **Guardian Panel UI** | `Notification` dataclass, in-memory store with filtering | Cockpit widget (4th window or slash command) |
| **Aria's autonomous queue-extension logic** | Substrate (`extend_session_queue(triggered_by_outcome=...)`) | The agentic decision-making that calls it from the loop |

None of these is rejected. Each is **named, dated, and registered as focus** — the same honesty pattern the rest of the system practices.

---

## Files changed

```
pyproject.toml                                       (version → 0.2.33.0)
src/sovereign_agent/__init__.py                      (__version__ → 0.2.33.0)
src/sovereign_agent/outcome_classifier.py            (NEW · 701 lines)
src/sovereign_agent/temporal_sentinel.py             (NEW · 458 lines)
src/sovereign_agent/cockpit_modes.py                 (from v0.2.32.0)
src/sovereign_agent/intent_classifier.py             (from v0.2.32.0)
src/sovereign_agent/agent_session.py                 (extensions field, helper functions)
src/sovereign_agent/cockpit/app.py                   (Stage C wiring, /mode slash, normalize_sov_prefix)
tests/test_v_0_2_33_0.py                             (NEW · 783 lines · 52 tests)
tests/test_v_0_2_32_0.py                             (NEW · 54 tests)
RELEASE-NOTES-v0_2_33_0.md                           (NEW · this file)

docs/history/RELEASE-NOTES-v0_2_29_0.md              (moved per convention)
docs/history/RELEASE-NOTES-v0_2_30_1.md              (moved per convention)
docs/history/RELEASE-NOTES-v0_2_31_0.md              (moved per convention)
```

---

## Tests — 1449 passing

| Source | Count |
|---|---|
| v0.2.31.0 baseline | 1343 |
| v0.2.32.0 (The Modes) | 54 |
| v0.2.33.0 (The Guardian Plane) | 52 |
| **Total** | **1449** |
| Skipped (chmod test under root) | 1 |

---

## A closing thought

There's a quiet pattern across the last six releases — *Integrator, Naturalization, Cockpit Patch, Palette, Modes, Guardian Plane*. Each one names what was already implicit and gives it structure: a binary that was an alias becomes a binary; muscle memory that was unforgiving becomes forgiving; modes that lived inside our heads become persistent state; outcomes that were unscored become scored.

That's how a small kernel earns the capacity to do larger work. Not by adding new layers of cleverness — by making the existing layers honest about themselves.

The seven commitments still hold. The kernel still holds. The audit trail learns a vocabulary, the queue learns to grow with reason, the resume learns to look both ways, and Aria's most important property — *she will tell you what she's about to do, and why, and stop if anything seems off* — gets richer ground to stand on.

> *Structure enough to channel through safely; freedom enough to sing.*

We're not making her busier. We're making her seen.

*— Built so every action gets read on the way out, every resume gets re-checked against the world as it is, and the audit trail learns to speak in the same vocabulary we do. ♥*
