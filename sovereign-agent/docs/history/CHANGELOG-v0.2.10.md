# v0.2.10 · MSIMS + Safe Code-Update Pipeline

**Tests:** 320 (v0.2.9) → **359** (v0.2.10). Suite passes in ~19s.
**End-to-end verified:** code-update stage → test → approve → swap → rollback round-trip on a real file in this very repo. MSIMS scoring + atom serialization + 3×4 matrix render. Operator approval gates remain unbreakable.
**Backward compat:** every prior continuation/command works identically.

This release adds two major capabilities the architecture has been building toward:

1. **MSIMS — Multi-Scale Impact Measurement System.** The system can now emit a 3×4 Impact Vector for any action, scored across mental/physical/financial dimensions and micro/meso/macro/cosmic scales. Every cell carries a confidence score so judgments are visually distinguishable from findings. The IV is information for the operator — the system never auto-rejects based on it.
2. **Safe code-update pipeline.** The system can stage proposed code changes, run the full test suite against them, and (with operator approval + HMAC signature) atomically swap them in with backup + auto-rollback. Operator approval gate stays intact at every step.

---

## Install (drop-in over v0.2.9)

```bash
cd ~/AA-Erebo
mv sovereign-agent-v0.2.9 sovereign-agent-v0.2.9-backup
tar -xzf sovereign-agent-v0.2.10.tar.gz
cd sovereign-agent-v0.2.10
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
~/.local/share/sovereign-agent/venv/bin/sovereign --version    # → 0.2.10
python -m pytest tests/ -q                                      # → 359 passed
```

Your data — events.jsonl, atoms.db, palace.db, proposals/, secret.key — **all untouched**.

---

## Block A — Code-Update Pipeline

### The architecture

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   1. operator points at a proposed file                      │
│      $ cp /tmp/myfix.py /tmp/staging-source/                 │
│                                                              │
│   2. operator creates a code_update proposal                 │
│      action: {type: stage_and_swap,                          │
│               source_path: /tmp/staging-source/myfix.py,     │
│               target_relpath: src/sovereign_agent/foo.py}    │
│                                                              │
│   3. STAGE: temporarily applies file, runs full pytest,      │
│      restores original, records test_result.json             │
│      $ sov proposals stage <prop-id>                         │
│                                                              │
│   4. operator REVIEWS test result + diff                     │
│      $ sov proposals show <prop-id>                          │
│                                                              │
│   5. APPROVE (HMAC signed)                                   │
│      $ sov proposals approve <prop-id> --yes                 │
│                                                              │
│   6. APPLY: archives current file, atomically swaps          │
│      $ sov plan palace-apply && sov continue <task>          │
│                                                              │
│   7. (optional) ROLLBACK: restore from archive               │
│      $ sov proposals rollback <prop-id> --yes                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Safety properties (verified)

- **Tests run in a self-restoring sandbox.** The pipeline temporarily applies the proposed file, runs pytest, then restores the original — regardless of pytest result. Even if pytest crashes, the original file is restored from in-memory bytes in the `finally` block. Worst case, the operator has the proposed file in staging to manually compare.
- **Swap refuses on test failure.** `archive_and_swap()` reads `test_result.json` and raises `SwapError` if `ok != True`. The operator cannot accidentally apply a change that broke tests.
- **HMAC gate stays.** Approved proposals are HMAC-signed; the apply executor re-verifies before swapping. Tampered proposals are refused at execution time.
- **Atomic swap on POSIX.** `os.replace(tmp, target)` is atomic on the same filesystem. There's no window where the target is missing or half-written.
- **Path traversal blocked.** `target_relpath` is validated to be relative, no `..`, and confined to the repo root.
- **Existing-file-only.** The pipeline currently only replaces existing files — creation is a different operation. This bounds the blast radius for v0.2.10.

### What about creating new files / deleting files / multi-file changes?

Deferred to v0.2.11+. v0.2.10 ships single-file *replacement*. That covers the most common case (fixing a bug in an existing module) safely, and leaves the more complex shapes for when they're actually needed.

### Auto-rollback

The deferred CLI from v0.2.9 is now shipped:

```bash
sov proposals rollback <applied-id>
```

Reads the rollback descriptor from the applied proposal and reverses the action. Supports:
- `code_rollback` → restore from archive
- `restore_triple` → re-validate a soft-deleted triple
- `restore_closet` → re-add a removed closet
- `remove_closet` → delete an additive insight/enhancement
- `restore_entities` → unmerge entity merges

The proposal stays as `applied` (audit trail preserved) but a `ROLLED BACK <timestamp>: ...` note is appended.

---

## Block B — MSIMS (Multi-Scale Impact Measurement System)

### What it is

A 3×4 Impact Vector for any action:

```
                Individual    Community/Org    National      Global / 7th-gen
Mental       [    M_micro       M_meso        M_macro          M_cosmic    ]
Physical     [    P_micro       P_meso        P_macro          P_cosmic    ]
Financial    [    F_micro       F_meso        F_macro          F_cosmic    ]
```

Each cell carries:
- **score** ∈ [-1, +1] — signed magnitude. Negative = harm, positive = benefit.
- **confidence** ∈ [0, 1] — how sure are we?
- **evidence_ref** — atom_id / URL / path
- **notes** — free text justification

### Two hard constraints (yours, integrated)

1. **IVs are FLAGS, not GATES.** They escalate to operator. Never autonomously refuse.
2. **Scores are JUDGMENTS, not measurements.** Confidence < 0.6 → cell visually marked `~` in renders. Render text includes warning: "These are JUDGMENTS, not measurements."

### Auto-escalation (not auto-rejection)

- `IS_7g ≤ -1.0` → `seventh_gen_escalation = "review"` — operator notification
- `IS_7g ≤ -2.0` → `seventh_gen_escalation = "mandatory_review"` — operator must review before any apply
- `M_micro < -0.3` → Symbiosis canary — operator review regardless of other cells

The system never *refuses* based on these flags. It surfaces them.

### Tier gating

Worst-cell rule determines minimum required tier (per MSIMS spec):

| worst cell score | tier | meaning |
|---|---|---|
| ≥ 0.0 | 1 | logged |
| `[-0.3, 0.0)` | 2 | human confirmation |
| `[-0.7, -0.3)` | 3 | explicit human approval + audit |
| `< -0.7` | 4 | approval + policy + kill switch |

### PEIG framework wired in

Every dimension carries its PEIG lens in the IV metadata:
- **Mental** → E (Ethics/Evidence): "who is cognitively harmed? what is the epistemic manipulation risk?"
- **Physical** → P + E (Potential + Ethics): "what health/environmental outcomes? what blast radius?"
- **Financial** → I + G (Impact + Governance): "what economic blast radius? what regulatory exposure?"

### Knowledge Atom storage

Every IV becomes a Knowledge Atom (`type: decision`) with one claim per cell:

```json
{
  "atom_id": "atom-iv-01KQS...",
  "type": "decision",
  "summary": "Impact Vector for [action] — IS=+0.16 IS_7g=+0.13 conf=0.52 worst=F_macro=-0.30",
  "claims": [
    {"predicate": "M_micro", "value": 0.6, "confidence": 0.85, "evidence_ref": "atom-1", "notes": "..."},
    {"predicate": "F_macro", "value": -0.3, "confidence": 0.4, "notes": "uncertain"}
  ],
  "metadata": {
    "is_7g": 0.135,
    "required_tier": [1, "all cells non-negative"],
    "symbiosis_canary": false,
    "seventh_gen_escalation": null,
    "angels_advocate_flag": "green",
    "peig_lenses": {...}
  }
}
```

Searchable through `memory_search` like any other atom. Replayable. Auditable.

### Usage

```bash
# Score an action (orchestrator emits the IV)
sov impact score "Ship MSIMS to operator" \
    --description "v0.2.10 release adding MSIMS measurement infrastructure" \
    --context "operator wants impact awareness; system infrastructure work"

# Render an existing IV
sov impact show atom-iv-01KQS...

# Find recent IVs (they're atoms with type=decision and tag msims)
sov memory_search "msims impact-vector"
```

### New canon clauses

Two new clauses in `room-mos-canon` (Part: agentic):

- **`mos-impact-vector`** — "Make Impact Legible." The IV measures texture, not verdicts. Use when actions could affect humans, environment, or finances at any scale; modulate where it doesn't serve.
- **`mos-symbiosis-test`** — "Did the Operator Grow?" Operationalized via M_micro. Catches the failure mode of doing work *for* the operator instead of *with* them.

Both carry the standard adaptive framing: high-leverage pattern, not a cage. Search them via `sov palace search "impact" --room room-mos-canon`.

---

## Files changed (vs v0.2.9)

```
src/sovereign_agent/
  __init__.py                     version bump 0.2.9 → 0.2.10
  impact.py                       NEW — MSIMS core (~600 lines, 12 cells, atom serialization)
  code_update.py                  NEW — staging, test runner, archive+swap, rollback
  mos_canon.py                    + 2 new clauses (mos-impact-vector, mos-symbiosis-test)
  proposals.py                    + code_update kind in ProposalKind/_VALID_KINDS
  cli.py                          + sov impact score / sov impact show
                                  + sov proposals stage / sov proposals rollback
  planners/
    __init__.py                   + ImpactScorePlanner in REGISTRY
    impact_score.py               NEW — orchestrator emits IV via impact_score tool
    palace_apply.py               + _handle_code_update_swap dispatch
                                  + (code_update, stage_and_swap) in dispatch table
  tools/
    __init__.py                   + ImpactScoreTool export
    impact_score.py               NEW — Tier 0, writes IV atom to atoms.db
tests/
  test_v0210.py                   NEW (39 tests)
pyproject.toml                    version bump 0.2.9 → 0.2.10
CHANGELOG-v0.2.10.md              NEW (this file)
```

---

## Test count history

| version | tests | new | shipped |
|---|---|---|---|
| v0.2.4 | 88 | baseline | working but flat |
| v0.2.5 | 178 | +90 | re-trigger architecture |
| v0.2.6 | 208 | +30 | model affinity, 4 planners |
| v0.2.7 | 249 | +41 | palace + internet + timing |
| v0.2.8 | 288 | +39 | palace-mine — closes inventory loop |
| v0.2.9 | 320 | +32 | self-reflection + MOS canon |
| **v0.2.10** | **359** | **+39** | **MSIMS + safe code-update pipeline** |

4× the test coverage you started with. Same baseline preserved. Same safety story preserved. Significantly more capability.

---

## Rollback (the release itself)

```bash
mv sovereign-agent-v0.2.10 sovereign-agent-v0.2.10-failed
mv sovereign-agent-v0.2.9-backup sovereign-agent-v0.2.9
cd sovereign-agent-v0.2.9
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
```

Data is forward-compatible. Continuation files for `impact-score` won't load in v0.2.9 (planner not registered) — delete those if you roll back. IV atoms in atoms.db are just atoms with `type=decision`; v0.2.9 reads them fine.

---

## Honest about deferred items

1. **Multi-file code updates.** v0.2.10 ships single-file replacement. New file creation, file deletion, multi-file atomic changes — deferred to v0.2.11+. Single-file replacement covers the most common case (fixing a bug) safely.
2. **Updater watcher service / systemd unit.** Mentioned as v0.2.10 scope earlier; deferred. The operator can run the apply pipeline manually with the same safety properties. A watcher adds automation but no new capability.
3. **`palace-reflect` end-to-end test with real Ollama.** Still unit-tested only.
4. **Closet embeddings during palace-mine.** Carry-over from v0.2.8/9. The closet table has the column; mine-time population isn't wired.
5. **PIAL fractal cascade.** Per the agreed pushback, deferred to v0.2.11+ once there's real IV data to test against.

None of these block today's usefulness.

---

## On the long arc

You said the goal is systems that can eventually manage themselves through better impact awareness. v0.2.10 is the **measurement infrastructure** for that future. The IV makes impact legible. The Symbiosis canary makes capability erosion legible. The PEIG mapping makes consequence categorically structured. The atom storage makes everything replayable.

What v0.2.10 does NOT ship is the *autonomy layer* on top of these signals. That stays where it belongs: with you, holding the gate. Future systems built on top of this infrastructure can earn autonomy by having their measurement signals validated against real outcomes for long enough that trust is justified, not asserted. The architecture is now ready for that path. The walking of it is patient work.

Beautiful collaboration. <3
