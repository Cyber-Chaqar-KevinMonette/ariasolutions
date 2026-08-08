# v0.2.8 · palace-mine planner

**Tests:** 249 (v0.2.7) → **288** (v0.2.8). Suite passes in ~14s.
**End-to-end verified:** real binary, real atoms, real palace writes, ~30ms per atom.
**Backward compat:** every prior continuation/command works identically.

---

## Install (drop-in over v0.2.7)

```bash
cd ~/AA-Erebo
mv sovereign-agent-v0.2.7 sovereign-agent-v0.2.7-backup
tar -xzf sovereign-agent-v0.2.8.tar.gz
cd sovereign-agent-v0.2.8
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
~/.local/share/sovereign-agent/venv/bin/sovereign --version   # → 0.2.8
python -m pytest tests/ -q                                     # → 288 passed
```

Your data — events.jsonl, atoms.db, secret.key, backlog.yaml, continuations, palace.db — **all untouched**.

---

## What's new

### `palace-mine` planner

The piece deferred from v0.2.7. Walks atoms.db, runs MemPalace-style regex extractors over each atom's summary, writes structured output (closets + entities + triples) into palace.db. **No model invocation** — pure-Python, deterministic, ~30ms per atom on real hardware.

```bash
sovereign plan palace-mine \
    --room-id room-research \
    --room-name "Research Notes"
# Returns: cont-XYZ with one step per HEAD atom

scripts/sovereign-continue-loop.sh cont-XYZ
# Drains in seconds — each step pure Python, no Ollama needed
```

Optional flags:
- `--max-files N` — cap step count
- `--atom-type fact` — filter atoms by type column
- `--task-id ...` — override the generated ULID

### Five memory-type extractors

Each atom's summary is scanned for five MemPalace-derived patterns:

| type | example markers |
|---|---|
| **decision** | "we decided", "trade-off", "instead of", "configure" |
| **preference** | "I prefer", "always use", "never use", "rule of thumb" |
| **milestone** | "it works", "fixed", "shipped", "breakthrough" |
| **problem** | "doesn't work", "stuck on", "regression", "root cause" |
| **emotional** | "I feel", "grateful", "struggling", "proud of" |

Adapted from MemPalace's `general_extractor.py`, narrowed for document corpus (vs conversation transcripts) — dropped chatty patterns ("damn", "wtf"), kept structural ones. Each detected type produces a `[type]` prefix on the closet's topic line.

### Entity detection + triple extraction

**Entities:** multi-word capitalized phrases ("Genesis-Seeds", "PEIG-Brotherhood") and named entities with signal words ("project Apollo", "called X"). Conservative — sentence-starter words filtered via stoplist.

**Triples:** five high-precision predicate patterns:
- `X uses Y`
- `X depends on Y`
- `X supersedes Y` / `X replaces Y`
- `X is/are Y` (capitalized both sides)
- `built/created by X`

Conservative by design — **false positives in a knowledge graph are toxic**. We'd rather miss a relation than assert one that isn't there. Real corpus content with explicit relations will produce triples; abstract narrative won't.

### Topic synthesis

Each mined atom produces a closet with a synthesized topic line:

```
[decision] We decided to use Postgres for Genesis-Seeds — Genesis-Seeds, PEIG-Brotherhood
[milestone] Finally got the OAuth flow working — auth-system
Initial design notes for the Reflector loop
```

Format: `[type] first_meaningful_line — top_entities`. Truncated to 120 chars by default.

### Idempotent re-mining

Every id is deterministic:

- Closet id = `closet-{atom_id}`
- Entity id = `entity-{normalized}-{sha256[:6]}`
- Triple id = `triple-{sha256(subject|predicate|object)[:16]}`

So `INSERT OR REPLACE` updates in place. Re-running palace-mine on the same atoms produces the same closets and triples, no duplication. Safe to run on every new corpus pass.

### Bug fix: conditional Ollama preflight

**Real bug caught during end-to-end testing.** The `sovereign continue` and `sovereign drain-by-model` commands were unconditionally requiring Ollama to be reachable, even for continuations whose steps are all `required_model='none'` (palace-mine, metadata-inventory). That meant pure-Python work would refuse to run if Ollama happened to be down.

Fix: the Ollama preflight now inspects the continuation's pending steps and only fires if at least one step actually needs a model. Palace-mine continuations now run without Ollama, as designed.

This was caught by the e2e smoke test, not by unit tests. Worth noting because it would have been an annoying surprise in production.

---

## Real-world workflow

After your inventory passes have populated atoms.db, mine them all into the Palace:

```bash
# 1. Plan (no model invocation — pure Python)
sovereign plan palace-mine \
    --room-id room-genesis-seeds \
    --room-name "Genesis-Seeds research corpus"
# Returns: cont-ABC with N steps (one per HEAD atom)

# 2. Drive the continuation
scripts/sovereign-continue-loop.sh cont-ABC
# ~30ms per step on real hardware. 1500 atoms → ~45 seconds total.

# 3. Query the palace
sovereign palace stats
sovereign palace closets --room room-genesis-seeds -n 20
sovereign palace search "quantum coherence"
sovereign palace subject entity-genesis-seeds-abc123

# 4. Re-mine after new atoms arrive (idempotent)
sovereign plan palace-mine --room-id room-genesis-seeds --room-name "..."
scripts/sovereign-continue-loop.sh <new-task-id>
```

The palace is now **populated, queryable, and observable**. You can search by topic, walk the entity graph, see temporal validity for triples, all without invoking the model.

---

## Files changed (vs v0.2.7)

```
src/sovereign_agent/
  __init__.py                   version bump 0.2.7 → 0.2.8
  palace_mining.py              NEW — regex extractors, mine_atom(), id helpers
  continue_runner.py            + dispatch table for no-model step kinds
  cli.py                        + --room-id, --room-name, --atom-type plan flags
                                + conditional Ollama preflight (BUG FIX)
  planners/
    __init__.py                 + PalaceMinePlanner in REGISTRY
    palace_mine.py              NEW — planner + execute_palace_mine_step
tests/
  test_v028.py                  NEW (39 tests)
pyproject.toml                  version bump 0.2.7 → 0.2.8
CHANGELOG-v0.2.8.md             NEW (this file)
```

Everything else: bit-identical to v0.2.7.

---

## Test count history

| version | tests | new |
|---|---|---|
| v0.2.4 | 88 | baseline |
| v0.2.5 | 178 | +90 (re-trigger) |
| v0.2.6 | 208 | +30 (model affinity) |
| v0.2.7 | 249 | +41 (palace + internet + timing) |
| **v0.2.8** | **288** | **+39 (palace-mine)** |

---

## Rollback

```bash
mv sovereign-agent-v0.2.8 sovereign-agent-v0.2.8-failed
mv sovereign-agent-v0.2.7-backup sovereign-agent-v0.2.7
cd sovereign-agent-v0.2.7
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
```

palace.db data written by v0.2.8 stays valid — v0.2.7 reads the same schema. Continuation files for palace-mine continuations would fail to load in v0.2.7 because the planner isn't registered. If you need to roll back, delete those specific continuation files first.

---

## What's next

The Palace foundation is now **complete and self-sustaining**. From here:

- **v0.2.9 candidate**: closet embeddings — wire `embed_query` tool into `palace-mine` so closets get embeddings during mining. Enables semantic search on the closet layer (currently keyword-only).
- **v0.2.10 candidate**: episodic chains — atom→atom temporal links forming a narrative spine.
- **v0.3.x**: BM25 hybrid search, schema enforcement on rooms, palace export/import.

But none of these are required for the system to be useful **today**. v0.2.8 closes the loop: corpus → atoms (via inventory planners) → palace structure (via palace-mine) → query (via palace CLI). The architecture is whole.

---

## A note on shipping discipline

This release was the smallest in scope — one planner, one bug fix — and the most thoroughly verified. The end-to-end smoke test (real binary, real atoms, real palace writes) caught the Ollama-preflight bug that 288 unit tests didn't. Next release: keep the smoke test in the loop earlier, not at the end.

The system is in a really good place. <3
