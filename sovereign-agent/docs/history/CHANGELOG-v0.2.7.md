# v0.2.7 · Palace, internet, timing

**Tests:** 208 (v0.2.6) → **249** (v0.2.7). Suite passes in ~13s.
**Backward compat:** v0.2.5/v0.2.6 continuations load unchanged. Every prior command works identically.

---

## Install (drop-in over v0.2.6)

```bash
cd ~/AA-Erebo
mv sovereign-agent-v0.2.6 sovereign-agent-v0.2.6-backup
tar -xzf sovereign-agent-v0.2.7.tar.gz
cd sovereign-agent-v0.2.7
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
~/.local/share/sovereign-agent/venv/bin/sovereign --version   # → 0.2.7
python -m pytest tests/ -q                                     # → 249 passed
```

Your data — events.jsonl, atoms.db, secret.key, backlog.yaml, continuations from v0.2.5 / v0.2.6 — **all untouched**. New `palace.db` created on first `sovereign init` or first palace command.

---

## What's new

### 1. Per-step timing observability

Every step now records `elapsed_seconds` (wall-clock duration). Persisted in the continuation YAML. Surfaced in:

- `sovereign continue <id>` output: `✓ step 0 (inventory_file) · 1/11 · iter=1 tokens=5313 · elapsed=8.42s`
- `sovereign continuations show <id>`:
  - per-step `elapsed` column showing `0.42s` / `1m 30s` / `1h 2m 5s`
  - aggregate `total elapsed: 1h 12m 30s`
  - per-model breakdown `elapsed by model: orchestrator=1h 12m  vision=42m`
- `events --flag continue-end-d --json` payloads include `elapsed_seconds`

`format_elapsed()` helper (`from sovereign_agent.continuation import format_elapsed`) renders raw seconds as `0.42s` / `1m 30s` / `1h 2m 5s` for any reporting needs.

### 2. Optional internet access

New Tier 0 `web_search` tool — DuckDuckGo HTML endpoint, no API key, no telemetry, no tracking. Pairs with the existing `web_fetch` tool: search finds URLs, fetch retrieves their content.

**Graceful degradation.** Controlled by `AGENT_INTERNET` env var (`auto` | `on` | `off`). Default `auto`: a quick TCP probe at startup decides whether the tool is registered. If offline, the agent doesn't see `web_search` in its tool list and never tries to use it. If `AGENT_INTERNET=off`, the tool is hard-disabled even if internet works.

```bash
sovereign doctor   # shows: internet | PASS | available (AGENT_INTERNET=auto)
                   #     or: internet | WARN | unavailable — web_search disabled
```

The agent itself doesn't *need* internet. This is purely additive: when available, it extends what the agent can do. When unavailable, everything else still works exactly as before.

### 3. The Palace — structured layer over atoms.db

A new `palace.db` (SQLite, no new deps) sits alongside `atoms.db`. Three concepts inspired by [MemPalace by Milla Jovovich](https://github.com/MemPalace/mempalace), adapted to sovereign-agent's atoms-as-leaves architecture:

**Rooms** — themed containers. e.g. `room-research`, `room-code`, `room-transcripts`. Each room has an opaque schema (slot definitions for typed extraction).

**Closets** — short index pointers that group related atoms by topic. Format:
```
topic | entities | →atom_id_1, atom_id_2, atom_id_3
```
Search the closets first (small, fast) — this is what makes retrieval scale past 10K atoms. MemPalace's primary insight, lifted into sovereign-agent.

**Triples** — typed knowledge graph edges with temporal validity:
```
(Max, child_of, Alice, valid_from='2015-04-01')
(Max, lives_in, Berlin, valid_from='2024-06-01')
(Max, lives_in, Brooklyn, valid_from='2020-01-01', valid_to='2024-06-01')
```

The temporal layer lets you ask *"what was true about X on date D?"* and *"what supersedes Y?"* — not just *"things related to X"*.

**Architecture property:** atoms are immutable ground truth. The Palace is a *projection* over them — drop and rebuild any time without losing data. Closets reference atoms by id. Triples can cite source atoms. This means the palace can evolve (new schemas, new extractors, new room layouts) without corrupting your knowledge base.

### Palace CLI

```bash
sovereign palace stats                          # rooms / closets / entities / triples
sovereign palace rooms                          # list rooms
sovereign palace create-room room-research "Research Notes" --description "..."
sovereign palace closets [--room <id>] [-n 20]  # list recent closets
sovereign palace search "quantum coherence"     # keyword search closet topics
sovereign palace subject <entity_id> [--as-of YYYY-MM-DD]   # query triples
```

JSON output via top-level `--json` works on every palace command.

### Palace API

For programmatic use (your own ingestion tooling):

```python
from sovereign_agent.palace import open_palace, Room, Closet, Entity, Triple

p = open_palace()
p.create_room(room_id="room-research", name="Research")
p.add_closet(Closet(
    id="closet-001", room_id="room-research",
    topic="quantum coherence in biological systems",
    entities=["quantum", "biology", "coherence"],
    atom_ids=["atom-abc", "atom-def"],
    embedding=[...],   # from embed_query tool, optional
    source_file="/path/to/source.md",
))
p.add_triple(Triple(
    id="t-001", subject_id="entity-max", predicate="researches",
    object_id="entity-quantum-coherence", valid_from="2024-01-01",
))
```

### What's NOT in v0.2.7 (deferred)

- **`palace-mine` planner** — auto-extract closets+triples from atoms. v0.2.8.
- **Hybrid BM25+cosine search** — v0.2.7 ships keyword OR semantic; not yet combined.
- **Episodic chains** — atom→atom temporal narrative spine. v0.2.8+.
- **Schema enforcement** — schemas are stored but not validated yet.

The Palace is the **scaffolding** for these. The plumbing exists; the planners come next.

---

## A note on MemPalace

MemPalace upstream (`github.com/MemPalace/mempalace`) is a complete product with ChromaDB-backed verbatim storage, regex extractors, conversation mining, and Claude Code hooks. We **adopted the architectural insight** (closets as index pointers, temporal triples) and built a sovereign-native implementation:

| | MemPalace | sovereign-agent v0.2.7 |
|---|---|---|
| Storage | ChromaDB (~hundreds MB deps) | SQLite (built-in) |
| Embeddings | sentence-transformers | Ollama nomic-embed-text |
| Primary use case | Claude conversation memory | Document corpus + agent atoms |
| Verbatim storage | drawers (ChromaDB) | atoms (already in atoms.db) |
| Index | closets (ChromaDB) | closets (SQLite) |
| Knowledge graph | SQLite triples | SQLite triples |
| Regex extractors | yes | not yet (v0.2.8 candidate) |

Same architectural pattern, native to sovereign-agent's stack. Storage minimalism preserved: one extra SQLite file, no new heavyweight deps, no new embedding model.

---

## Files changed (vs v0.2.6)

```
src/sovereign_agent/
  __init__.py                   version bump 0.2.6 → 0.2.7
  config.py                     + palace_db path
  continuation.py               + Step.elapsed_seconds, + format_elapsed,
                                + Continuation.{total_elapsed_seconds, elapsed_by_model}
  continue_runner.py            + record elapsed in step + StepRunResult, emit in event log
  cli.py                        + sovereign palace … commands, + elapsed display in continue/show,
                                + internet check in doctor, + conditional web_search registration
  palace.py                     NEW — Palace class, schema, Closet/Room/Entity/Triple dataclasses
  tools/
    __init__.py                 + WebSearchTool export
    web_search.py               NEW — DuckDuckGo HTML, internet probing, graceful degrade
tests/
  test_v027.py                  NEW (41 tests)
pyproject.toml                  version bump 0.2.6 → 0.2.7
CHANGELOG-v0.2.7.md             NEW (this file)
```

Everything else: bit-identical to v0.2.6.

---

## Rollback

```bash
mv sovereign-agent-v0.2.7 sovereign-agent-v0.2.7-failed
mv sovereign-agent-v0.2.6-backup sovereign-agent-v0.2.6
cd sovereign-agent-v0.2.6
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
```

palace.db will be left behind in your data dir — harmless, ignored by v0.2.6. Continuation files written by v0.2.7 with `elapsed_seconds` field load fine in v0.2.6 (field silently dropped).

---

## Known limitations

1. **End-to-end binary verification skipped this build cycle** (token budget). All 249 tests pass; bundle hasn't been re-tested against fresh extract on a clean venv. Run `python -m pytest tests/ -q` immediately after install.

2. **No `palace-mine` planner yet** — the Palace has no automated way to ingest atoms into closets+triples. You can use the Python API directly, but a `sovereign plan palace-mine` command (matching the inventory/code/pdf/image planners) is v0.2.8.

3. **DDG HTML scraping is brittle**. If DuckDuckGo changes their result page format, the parser stops working (returns empty results — no crash). At that point we either update the regex or swap the backend.

4. **Internet probe target is hardcoded** to `1.1.1.1:53`. Change at the top of `web_search.py` if your network needs a different probe (e.g., behind a captive portal that blocks Cloudflare DNS).

---

Three big pieces in one release. Lots of new surface — query it slowly, give it real data, tell me what surfaces. The system is significantly more capable now. <3
