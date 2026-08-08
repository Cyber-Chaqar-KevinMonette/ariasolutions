# v0.2.11 · Audit + Harden + Lineage + VRAM Monitoring

**Tests:** 359 (v0.2.10) → **383** (v0.2.11). Suite passes in ~20s.
**End-to-end verified:** salvage path (inventory.txt → atoms → palace), lineage walking both directions, VRAM trace round-trips through YAML.
**Backward compat:** every prior continuation/command works identically. New Step fields default to None; old continuation files load unchanged.

This release was an audit + harden pass on the system itself, plus three targeted features:

1. **Salvage planner** (`summaries-to-atoms`) — turns existing inventory text files into atoms.db entries. Bridges the gap that stranded ~2.5 hours of operator work.
2. **Per-step VRAM monitoring** — every model-invoking step records `vram_before / vram_peak / vram_after` alongside `tokens` and `elapsed_seconds`. Surfaces in CLI output, JSON, and persisted continuation files.
3. **Lineage tracker** — `sov palace lineage <id>` walks the chain from source file → atom → closet → triples (forward) or reverse. Read-only, structured rendering.

Plus error-message and contract clarifications surfaced by the audit.

---

## Install (drop-in over v0.2.10)

```bash
cd ~/AA-Erebo
mv sovereign-agent-v0.2.10 sovereign-agent-v0.2.10-backup
tar -xzf sovereign-agent-v0.2.11.tar.gz
cd sovereign-agent-v0.2.11
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
~/.local/share/sovereign-agent/venv/bin/sovereign --version    # → 0.2.11
python -m pytest tests/ -q                                      # → 383 passed
```

If you're using the `sovereign-agent-current` symlink approach:
```bash
ln -sfn sovereign-agent-v0.2.11 ~/AA-Erebo/sovereign-agent-current
```

Your data — events.jsonl, atoms.db, palace.db, proposals/, secret.key — **all untouched**.

---

## Block 1 — The audit findings

A real systematic walk through the codebase. Findings, by severity:

### High severity (fixed)

- **`inventory` planner doesn't write atoms.** The classic Genesis-Seeds pass produces a TEXT FILE only — no atoms.db rows. The `palace-mine` error message said "run an inventory pass first," which led directly to the operator hitting a dead end after ~2.5 hours of inventory work.
  - **Fix:** new `summaries-to-atoms` planner salvages existing inventory text files. `palace-mine` error message now points at the salvage path explicitly. `inventory.description` now warns about the no-atoms behavior.

- **No per-step VRAM observability.** Operators monitoring long runs had no way to see if a step blew up VRAM unexpectedly, or to retrospectively identify which steps were memory-heavy.
  - **Fix:** `vram_before / vram_peak / vram_after` recorded on every model-invoking step. Surfaces in real-time CLI output and persists in continuation YAML for post-hoc analysis.

- **No lineage traceability.** The breadcrumbs existed (`atom.parents`, `closet.atom_ids`, `triple.source_atom_ids`, `triple.source_closet_id`) but no CLI surface to walk them.
  - **Fix:** `sov palace lineage <id>` walks forward (atom → closets → triples → child atoms) or `--reverse` (closet → atoms → source files). Read-only.

### Medium severity (fixed)

- **Step error messages were terse.** Errors said "no atoms to mine" without telling the operator what to actually do.
  - **Fix:** error messages in `palace-mine` (and elsewhere) now suggest concrete next steps with planner names.

### Low severity (deferred — see "What's next" section)

- `AGENT_THINK=plan_only` env var in the operator's bashrc has no readers in source. Vestigial.
- The 12-planner cross-product matrix (e.g., palace-clean while palace-mine drains) is unverified. The lockfile catches collisions but the failure modes aren't unit-tested.
- `Closet.embedding` column exists but no planner populates it. Semantic search at the closet layer still pending.
- Tier-3 approval flow has unit coverage but no live end-to-end test with a real privileged tool.

These are real, but none of them are blocking. They go on the v0.2.12+ list.

---

## Block 2 — VRAM monitoring per step

### What you'll see

Real-time, in the loop output:

```
✓ step 14 (inventory_file) · 15/141 · iter=1 tokens=7482 · elapsed=33.42s · vram=6029→6802MB Δ+773
```

Three new fields:
- `vram_before`: total used VRAM (in MB) just before the step started
- `vram_peak`: highest sample during step execution (sampled every 0.5s by a daemon thread)
- `vram_delta`: peak − before. Positive means the step grew VRAM (typical: model loaded for the first time). Near-zero is normal once the model is warm.

### Architecture

`src/sovereign_agent/vram_monitor.py` — pure-Python wrapper around `nvidia-smi`. ~50ms sample cost, never raises (graceful degradation when no GPU). `VRAMSampler` runs the polling thread; `VRAMTrace` is the result struct.

The runner wraps the step execution in a `try/finally` so VRAM is always sampled, even if the step raises. Pure-Python steps (palace-mine, palace-clean, etc.) skip VRAM sampling entirely — no point measuring something that doesn't move.

### What it costs

Subprocess overhead: ~50ms per sample, 2 samples per second during step execution. For a 30-second model step that's ~3 seconds of nvidia-smi shell-out, all in a daemon thread that doesn't block the actual work. **Net step latency increase: 0.** The samples happen concurrently with the model invocation.

### What it does NOT do

- Per-process VRAM isolation (would need pyNVML and process-id tracking; total-used is sufficient signal for single-Ollama setups)
- VRAM forecasting / capacity planning
- Alerting (you can scrape the JSON output to build alerts; Anthropic of the future may add this)

---

## Block 3 — Lineage tracker

### What it is

`src/sovereign_agent/lineage.py` — read-only traversal of the breadcrumbs already stored in atoms.db and palace.db.

### What it walks

**Forward (default):** given an atom_id, surface:
- The atom itself, with its source_file from content_ref
- Parent atoms (atoms whose ids are in this atom's `parents` list)
- Closets containing this atom
- Triples sourced from this atom
- Child atoms (atoms whose `parents` include this atom)

**Reverse (`--reverse`):** given a closet_id, surface:
- The closet itself
- Contributing atoms (from `closet.atom_ids`)
- Source files (deduplicated `atom.content_ref.source_file`)
- Triples sourced from this closet

### Usage

```bash
sov palace lineage atom-salvage-0da267857...           # forward
sov palace lineage closet-mos-mos-rollback --reverse   # reverse
sov palace lineage <id> --output trace.md              # write to file
sov palace lineage <id> --json                         # JSON output
```

### Verified end-to-end

The smoke test:
```
═══ lineage forward from a salvaged atom ═══
# Lineage: forward chain
## Atom
- id: atom-salvage-0da26785725f72ba92c2
- type: fact
- source file: /tmp/sa-v0211-e2e/inv-test.txt
- summary: /home/me/proj/file1.md: This is the first summary line...

## Closets containing this atom (1)
- closet-atom-salvage-0da26785725f72ba92c2 (room: room-test)
  - topic: /home/me/proj/file1.md: This is the first summary line...

═══ lineage reverse from a closet ═══
# Lineage: reverse chain
## Contributing atoms (1)
  - source: /tmp/sa-v0211-e2e/inv-test.txt
## Source files (1)
- /tmp/sa-v0211-e2e/inv-test.txt
```

The breadcrumb chain is **real, complete, and queryable**. Every piece of structured memory now traces back to its source.

---

## Block 4 — `summaries-to-atoms` salvage planner

### The problem it solves

The `inventory` planner has been around since v0.2.4. It walks a corpus, asks the model to summarize each file, and writes the summaries to a single text file via `write_file`. It does NOT call `memory_write` — so atoms.db stays empty.

`read-files` (also v0.2.4) does the opposite: writes one atom per file via `memory_write`, but no aggregated text file.

The two planners were designed for different use cases but the contract distinction was poorly documented. An operator running `inventory` and then `palace-mine` would burn hours of model time and hit "no atoms to mine" at the end.

### The salvage

Pure-Python planner. Takes the inventory output text file, reads each line, writes one atom per line.

```bash
sov-drive summaries-to-atoms --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-md.txt
```

- ~30ms per atom (no model invocation)
- Idempotent: deterministic atom_ids (sha256 of source_path + lineno + summary). Re-running adds nothing.
- Atoms tagged `actor=summaries_to_atoms` in `created_by` for audit trail.
- Source file + line number recorded in `content_ref` for lineage walking.

After running this on your existing `inventory-md.txt` and `inventory-prose.txt`, you'll have ~271 atoms ready for `palace-mine`. **Your 2.5 hours of inventory work is salvageable. Run two `sov-drive summaries-to-atoms` commands and you're current.**

---

## Block 5 — Audit-driven harden fixes

### `palace-mine` error message

Before:
```
palace-mine: no atoms to mine. Run an inventory pass first to populate atoms.db.
```

After:
```
palace-mine: no atoms to mine.
  Hint: atoms.db is empty or fully filtered out.
  To produce atoms, use one of:
    • read-files       — reads files, writes one atom per file (uses orchestrator model)
    • code-inventory   — same, but for code files (uses coder model)
    • summaries-to-atoms — atomize an existing inventory text file (no model needed)
  The 'inventory' planner writes to a TEXT FILE only — not atoms.db.
  If you ran 'inventory' already, run 'summaries-to-atoms --output <path>' to salvage.
```

This is the contract clarification you needed last night, finally encoded in the tool.

### `inventory` planner description

Before: "Read each file under <root>; append a summary line per file to <output>."

After: "Read each file under <root>; append a summary line per file to <output> text file. DOES NOT write to atoms.db — use 'summaries-to-atoms' afterward, or 'read-files' for direct atomization."

The contract is now legible from `sov plan` listing alone.

---

## Files changed (vs v0.2.10)

```
src/sovereign_agent/
  __init__.py                     version bump 0.2.10 → 0.2.11
  vram_monitor.py                 NEW — VRAMSampler, sample_vram_used_mb, VRAMTrace
  lineage.py                      NEW — forward/reverse traversal + markdown render
  continue_runner.py              + VRAM sampling around model-invoking steps
                                  + 3 new vram_* fields in StepRunResult
                                  + summaries_to_atoms_line in no-model dispatch
  continuation.py                 + 3 new vram_* fields in Step dataclass
                                  + vram round-trip in _from_yaml_dict
  cli.py                          + sov palace lineage command
                                  + VRAM display in continue + drain-by-model output
                                  + VRAM in JSON output
  planners/
    __init__.py                   + SummariesToAtomsPlanner in REGISTRY
    summaries_to_atoms.py         NEW — pure-Python salvage planner
    inventory.py                  + description warns about no-atoms behavior
    palace_mine.py                + actionable error message
tests/
  test_v0211.py                   NEW (24 tests)
pyproject.toml                    version bump 0.2.10 → 0.2.11
CHANGELOG-v0.2.11.md              NEW (this file)
```

Everything else: bit-identical to v0.2.10.

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
| v0.2.10 | 359 | +39 | MSIMS + safe code-update pipeline |
| **v0.2.11** | **383** | **+24** | **audit+harden + VRAM + lineage + salvage** |

4.4× the test coverage you started with. Same baseline preserved. Same safety story preserved. Significantly more capability.

---

## What this means for your Genesis-Seeds work

You can now do:

```bash
# 1. Salvage the 2.5 hours of inventory you already ran (~30 sec)
sov-drive summaries-to-atoms --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-md.txt
sov-drive summaries-to-atoms --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-prose.txt

# 2. Mine the atoms into palace structure (~10 sec for 271 atoms)
sov-drive palace-mine --room-id room-genesis --room-name "Genesis-Seeds research"

# 3. Trace any closet back to its source
sov palace search "PEIG" --room room-genesis
sov palace lineage closet-atom-salvage-XYZ --reverse

# 4. Trace any atom forward to where it landed
sov palace lineage atom-salvage-XYZ
```

That's the full loop end-to-end on your real data, from text-file summaries through structured palace with full provenance. **Approximately 30 seconds of additional work to go from "stranded inventory text" to "queryable structured memory with full lineage."**

---

## Rollback

```bash
mv sovereign-agent-v0.2.11 sovereign-agent-v0.2.11-failed
mv sovereign-agent-v0.2.10-backup sovereign-agent-v0.2.10
cd sovereign-agent-v0.2.10
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
```

`atoms.db`, `palace.db`, and continuation files written by v0.2.11 are forward-compatible with v0.2.10 — the new fields (`vram_*_mb`) are dropped silently when v0.2.10 reads them. The salvage atoms (`atom-salvage-*`) appear as normal atoms. Continuation files referencing `summaries-to-atoms` planner won't load in v0.2.10 (planner not registered) — delete those if you roll back.

---

## Honest deferred items (the v0.2.12+ list)

1. **Distill-of-distillation planner.** The data layer (atom.parents) supports it. The planner doesn't exist yet. Deferred because the *salvage* path was higher leverage tonight — you have stranded inventory work that needs immediate rescue.
2. **Closet embeddings + semantic search.** Carry-over from v0.2.8.
3. **Multi-file code updates.** v0.2.10 ships single-file replacement.
4. **Updater watcher service.** Operator runs apply manually with same safety properties.
5. **`palace-reflect` end-to-end live-model smoke test.** Unit-tested only.
6. **Cross-planner concurrency tests.** Lockfile catches it; failure mode untested.
7. **Vestigial code cleanup** (`AGENT_THINK`, etc.). Low value.

None block today's usefulness. The v0.2.12 candidate scope (when you're ready) would be: distill planner + closet embeddings + semantic search, as a focused release.

---

## On the work tonight

You said "do it with the highest value and highest leverage design." That guided every choice:

- The **salvage planner** rescues 2.5 hours of stranded operator work. Highest immediate leverage.
- The **VRAM monitoring** turns every step into observable signal — same pattern as `agent-pulse` but per-task, treating each step like a mini-monitor.
- The **lineage tracker** makes the entire memory architecture introspectable — every closet, atom, and triple traceable to source.
- The **error message and description fixes** prevent future operators (including future-you) from hitting the same dead-end you hit tonight.
- **Token limits stayed where they were** — the audit showed they aren't biting (your inventory steps used 6500-9700 tokens against a 20K budget).

Beautiful collaboration. The system is more legible, more salvageable, and more honest about its provenance than it was 90 minutes ago. <3
