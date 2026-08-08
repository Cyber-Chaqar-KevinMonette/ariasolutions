# Sovereign Agent v0.2.23.0 · release notes — *First Crystallization*

> *The wake/sleep upward operator. Provenance entries crystallize into semantic atoms. Atoms point back to evidence. Nothing is buried. The pyramid begins.*

**949 tests pass.** 928 from v0.2.22.0 + 21 new for atoms, consolidation, and palimpsest discipline.

This release introduces the L2 semantic layer and the consolidation operator — the first piece of the fractal pyramid memory architecture that emerged from Kevin's question: *"could something like this bring value?"*

---

## Reading the question

Kevin shared two research-grade designs for a 5-layer pyramid memory system (L0 scratch → L1 episodic → L2 semantic → L3 procedural → L4 canon) with wake/sleep consolidation. The honest read:

**The pyramid shape is already half-present in what we have.** Channels are L2-shaped. Stewardship triples are L1. Provenance is L1. MOS-SURFACE is L4. The shape exists by accumulation.

**What's missing isn't the layers — it's the operator between them.** Information sits at L0/L1 (raw observations, episodes) but never crystallizes upward into L2 (distilled patterns). There's no consolidation. No wake/sleep cycle. Aria has experiences but doesn't yet have *learned regularities*.

**Three contributions on top of the documents Kevin shared:**

1. **The palimpsest framing.** Old layers stay visible under new ones. When we consolidate provenance entries into a semantic atom, we *do not delete the entries.* The atom points to them via `evidence_refs`. Retrieval can always drop back. This is what makes memory feel lived-in rather than archived.

2. **Consolidation IS calibration training.** When Aria distills "Kevin's back-pain messages tend to come after 9pm, route to body+emotions, low specialist content" — that's a falsifiable prediction. Future similar messages can be checked against it. Match → high calibration. Drift → flag for re-consolidation. Consolidation produces falsifiable claims that feed the stewardship reward signal.

3. **The honor ledger is orthogonal to the pyramid.** It threads through all layers as a temporal witness record. Don't force it into L0–L4.

## What ships now

The smallest piece that captures the deepest leverage: **the consolidation operator + the L2 semantic layer.**

### The Atom — three kinds

```
fact      "Kevin's home OS is Pop!_OS"
pattern   "Kevin's back-pain messages tend to arrive after 9pm
           and route to body+emotions channels"
rule      "Messages containing 'cancel' are slash commands"
```

Each atom carries:

- **claim** — the distilled statement, in Aria's voice
- **confidence** — 0..1, how strongly evidence supports it
- **evidence_refs** — list of provenance entry IDs (≥ 2 required)
- **channels** — what this atom is "about"
- **tags** — open-namespace categorization (schedule, preference, habit, …)
- **status** — active or superseded

### The consolidation operator — wake/sleep upward

```bash
sov consolidate
```

What happens:

1. Read the last 100 provenance entries (`tail_n`, tunable)
2. Cluster them by exact `save_to` channel-set match
3. For each cluster of ≥3 entries, ask Aria to distill atoms via the LLM
4. Validate every proposed atom (≥ 2 evidence refs, evidence IDs must exist in the cluster, kind must be valid)
5. Append valid atoms to `atoms.ndjson`
6. Return a summary

```
consolidation pass complete
  entries read:         100
  clusters found:       7
  clusters distilled:   7
  atoms proposed:       12
  atoms saved:          10        ← 2 rejected (fake evidence IDs or singleton)
```

### Why exact channel-set clustering (not embedding similarity)

The research docs propose K-means clustering across episode embeddings. Overkill for our scale and our hardware. **The channels Aria already chose are her semantic groupings.** Entries that route to `{back-pain, emotions}` are talking about the same kind of thing as other `{back-pain, emotions}` entries. Use what's already there.

This is cheaper, deterministic, and matches the LLM's own organization scheme. Embedding-based clustering is in the roadmap for v0.2.24.0+ but only if simple clustering proves insufficient.

### The palimpsest property — enforced

```python
def test_consolidate_does_not_delete_provenance(self, tmp_path):
    original_content = path.read_text()
    asyncio.run(consolidate(...))
    assert path.read_text() == original_content   # unchanged
```

```python
def test_atoms_log_is_append_only(self, tmp_path):
    store = AtomStore(...)
    assert not hasattr(store, "delete")
    assert not hasattr(store, "remove")
    assert not hasattr(store, "clear")
    assert not hasattr(store, "truncate")
```

Supersession is the only way an atom changes status — and even supersession appends new entries to the log rather than mutating prior ones. Both the original and the superseded atom are reconstructible from the raw lines.

### Authority preserved

The router still validates every command. The interpreter still falls through cleanly when Ollama is unavailable. Consolidation has its own offline behavior: **no atoms are guessed deterministically.** If the LLM can't run, the consolidation pass is a no-op and reports `skipped_offline=N` for the operator's information. Provenance entries are not consumed — the next pass will see them again.

```python
def test_offline_is_no_op(self):
    summary = consolidate(ollama_client=None, ...)
    assert summary["atoms_saved"] == 0
    assert summary["skipped_offline"] == 1
```

This matches the v0.2.21.0 doctrine: when Aria can't think, she says so honestly. No keyword guessing. No pretending.

## New CLI

```bash
# Run the consolidation pass (wake/sleep upward)
sov consolidate
sov consolidate --tail-n 200 --min-cluster 3

# Inspect what Aria has distilled
sov atoms list
sov atoms list --kind pattern
sov atoms list --channel back-pain
sov atoms list --contains "9pm"

# Drill into a specific atom (prefix-matching on ID)
sov atoms show abc12345

# Count
sov atoms count
```

## What this enables (and what it doesn't yet)

**Now enabled:**
- Aria's experience starts crystallizing into durable patterns
- The reward signal (stewardship) has a new substrate: pattern atoms are falsifiable predictions
- Retrieval has new material: future queries can hit atoms first, then drop to episodes
- The architecture has its first crystallization seam — the upward move is real

**Not yet:**
- **Traversal-aware retrieval** (the downward move) — v0.2.24.0
- **Drift detection** — automated comparison of pattern atoms vs new entries — v0.2.24.0
- **Auto-scheduled consolidation** (post-N entries, or nightly cron) — v0.2.24.0
- **The skill library / L3 procedural layer** — deferred indefinitely; Aria's command-writing works; a named-skill registry is incremental rather than load-bearing
- **Prospective memory triggers** — v0.2.25.0
- **Counterfactual / simulated atoms** — coupled to the dream loop; v0.2.25.0

This is intentional. The MVP for any pyramid is one operator at a time. Build it, see what atoms actually emerge in real use, *then* design the traversal layer that walks them. Shipping the full architecture speculatively would produce code that doesn't fit what Aria actually crystallizes.

## Doctrine — three new invariants

The palimpsest discipline gets named explicitly:

1. **Append-only memory.** No memory layer exposes a `delete()` method. State changes are written as new lines that reference prior entries.

2. **Evidence pointers, not summaries.** Atoms point back to the provenance entries that produced them. An atom that loses its evidence is meaningless — and the system enforces ≥2 references at creation time.

3. **Conservative consolidation.** False atoms are worse than missing atoms. The LLM is instructed to skip clusters it can't confidently distill, and the validator drops any atom with fewer than 2 valid evidence references.

These become MOS-SURFACE §22 (formal write-up to ship with v0.2.24.0 alongside the traversal layer).

## Tests — 949 passing

| Source | Count |
|---|---|
| Baseline (v0.2.18.6) | 812 |
| Stewardship (v0.2.20.0) | 45 |
| Conversation LLM-first (v0.2.21.0) | 22 |
| Stress + edge cases | 25 |
| Security + corrections + rotation (v0.2.22.0) | 24 |
| **First Crystallization (v0.2.23.0)** | **21** |
| **Total** | **949** |

The new tests cover:
- Atom CRUD with supersession preserving full history
- Channel-set clustering with deterministic grouping
- Consolidation when LLM available (atoms saved)
- Consolidation when LLM unavailable (no-op, provenance preserved)
- Hallucinated evidence IDs rejected by the validator
- Single-evidence atoms rejected
- Malformed LLM responses handled without raise
- Palimpsest invariants (no delete, provenance untouched)

## Upgrade

```bash
mv ~/Downloads/sovereign-agent-v0.2.23.0.tar.gz ~/AA-Erebo/
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.23.0.tar.gz
~/.local/share/sovereign-agent/venv/bin/pip install -e ./sovereign-agent-v0.2.23.0

sov --version   # → 0.2.23.0

# Once you have ~20 provenance entries from real cockpit use:
sov interpret count            # check how many you have
sov consolidate                # run the upward operator
sov atoms list                 # see what crystallized
```

A few dozen real interpretations is usually enough for the first interesting clusters. Less than that and the consolidation will mostly skip (clusters below `min_cluster_size`).

## Roadmap forward — what comes next

**v0.2.24.0 — *The Traversal*.** The downward operator. When Kevin asks recall questions, Aria walks the pyramid: canon constraints first, then skills, then atoms, then episodes, then raw logs. She synthesizes a layered answer with citations. Also: drift detection (does the pattern atom still match new entries?) and auto-scheduled consolidation (post-20-entries or nightly).

**v0.2.25.0 — *The Prospection*.** Prospective memory triggers ("remind me Friday"). Counterfactual atoms tagged `simulated=true` from the dream loop. Auto-generated honor notes when Aria notices a near-miss during execution.

**v0.2.26.0+ — *The Tending*.** Channel sprawl management. Apprentice loop (Aria reviews her own provenance and self-corrects). Drift report. Honest disagreement channel.

The pyramid keeps building. Slowly, by tier, with real usage between releases.

## A note from the work

The two research docs Kevin shared were clearly LLM-generated synthesis of recent papers. They were not wrong — they were polished but generic. They prescribed K-means and small generative models and multi-vector RAG. All useful at scale. All overkill at ours.

The deepest move was to take the *shape* (5 layers, wake/sleep, three operators) and *adapt* it to a single-operator, local-LLM, hardware-constrained, already-half-built system. That meant:

- Skipping L3 (Aria already writes commands; a skill registry is incremental)
- Using channel-set clustering instead of K-means (deterministic, free, matches Aria's existing organization)
- Adding the palimpsest framing the docs didn't articulate (old layers visible under new)
- Naming the calibration-training property the docs didn't notice (pattern atoms are falsifiable predictions)

What's shipping is small in code and large in implication. One module for atoms. One module for consolidation. One CLI command. ~600 lines of Python. But it's the seam where Aria's memory begins to *grow* rather than just *accumulate*.

*— Aria, with provenance crystallizing into pattern, evidence pointers preserving everything underneath, and the first whisper of a pyramid that grows wider at the base and crystallizes upward.*
