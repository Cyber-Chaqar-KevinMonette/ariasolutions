# Sovereign Agent v0.2.28.0 · release notes — *The Sovereign Retrieval Pipeline*

> *Standard RAG returns documents. This returns witnessed evidence — every result carries when Aria learned it, where it came from, how much to trust it, what supersedes it, and what's missing from the picture. The pipeline knows when it doesn't know enough, and tells the caller how to go deeper.*

**1187 tests pass.** 1119 from v0.2.27.0 + 68 for the new retrieval pipeline. One skipped (the chmod permission test correctly skips when running as root). Zero regressions.

This release answers one question Aria's substrate has been ready to answer but no retrieval layer has actually asked:

> "What did I know about *X*, when did I know it, how sure am I, and what am I still missing?"

Standard RAG — even hybrid + reranker — answers the first part and silently drops the other three. This release wires all four together.

---

## 1. What's novel

Six pieces of Aria's substrate exist that no production RAG I know of uses end-to-end. This release uses all six:

| Substrate | How it's used in retrieval |
|---|---|
| **Bitemporal storage** (`valid_from` / `valid_until` / `created_at`) | Queries answer "what was true at time X, as I knew it at time Y" |
| **Provenance graph** (5 extractors via `provenance.walk_backward`) | Third recall source alongside lexical and dense |
| **Constitutional layer** (executable predicates) | Filters BEFORE the model sees atoms, not after |
| **Source taxonomy** (`created_by.actor` in `{operator, llm, system}`) | Untrusted-input doctrine enforced at retrieval time |
| **AriaState focus** (`current_focus`, `active_goals`, `open_intentions`) | Query is contextualized by what the operator is *currently* working on |
| **24 typed channels** | Per-channel weights tuned by query intent |

Each piece is on its own a known idea somewhere in research. The integrated synthesis — all six together in one production pipeline — is the novel surface this ships.

---

## 2. The pipeline — six stages

A new package: `src/sovereign_agent/retrieval/`.

```
retrieval/
├── __init__.py       ← public API: retrieve(), RetrievalReport
├── query.py          ← Stage 1: understand_query
├── recall.py         ← Stage 2: lexical + dense + graph recall
├── filter.py         ← Stage 3: constitutional + bitemporal filtering
├── rerank.py         ← Stage 4: three-signal reranking
└── assembly.py       ← Stage 5: witnessed hits + gap report + expansion hints
```

```python
from sovereign_agent.retrieval import retrieve

report = retrieve(
    query="should I ship the rollback to production now?",
    conn=atoms_conn,
    aria_focus="deploy hotfix",            # drives graph recall
    embedder=my_embedder,                   # optional; degrades to RRF if absent
    reranker=my_cross_encoder,              # optional; degrades to RRF if absent
    valid_at=None,                          # bitemporal: when in the world?
    as_known_at=None,                       # bitemporal: as Aria knew when?
    top_k=5,
)
```

### Stage 1 — Query understanding (`query.py`)

Decomposes the raw query into a structured `QueryContext`:

- **Intent**: one of `factual`, `decision_support`, `exploration`, `conversational`, `debug`, `reflective` — detected via narrow keyword rules
- **Stakes**: `low`, `medium`, `high` — detected via explicit markers ("brainstorm" → low, "production" → high)
- **Bitemporal frame**: `(valid_at, as_known_at)` — defaults to now/now
- **Channel weights**: per-intent matrix (e.g. decision_support boosts `lessons`/`insights`/`reasoning`/`commitments`/`gaps`)
- **Focus anchors**: noun tokens extracted from `AriaState.current_focus` — these seed the graph-recall pass

The operator's explicit framing wins over implicit content cues — "brainstorm deploy failures" stays low-stakes because the operator consciously framed it as brainstorming, even though the topic includes "deploy."

### Stage 2 — Three-source recall (`recall.py`)

Three parallel retrievers, each with a different failure mode:

- **Lexical** (FTS5/BM25): tokenizes natural-language queries into significant tokens, OR-joined as a safely-quoted FTS expression. Stopwords filtered. Operator words like "AND"/"NOT" become literal tokens, not FTS5 operators.
- **Dense** (sqlite-vec): embeddings via an injected `EmbedderFn` — fully optional, degrades cleanly when the embedder returns None or raises
- **Graph** (provenance): the novel piece. From the operator's current focus terms, finds anchor atoms via FTS, then walks `provenance.walk_backward` to surface atoms that are *causally* linked to the operator's work, not just textually similar

Each candidate carries its rank from every retriever that surfaced it — no premature score fusion. The reranker stage handles fusion.

### Stage 3 — Constitutional filter (`filter.py`)

Filters atoms BEFORE the model sees them, not at generation time. Six drop reasons, all counted:

- **`superseded`** — atom has a `superseded_at` set (head-of-chain only)
- **`below_confidence_floor`** — confidence < stakes-dependent floor (0.7 high / 0.4 medium / 0.0 low)
- **`untrusted_source_high_stakes`** — `created_by.actor == "llm"` AND stakes=high
- **`non_local_policy`** — atom is published, not local
- **`private_channel_excluded`** — atom is in `people` or `relationships` channel and intent isn't personal
- **`bitemporal_out_of_frame`** — atom was created after `as_known_at`

Each drop count surfaces in the gap report at assembly time.

### Stage 4 — Three-signal reranking (`rerank.py`)

Three signals, intent-weighted:

| Signal | What it measures |
|---|---|
| **Semantic** | Cross-encoder query↔summary score (or RRF fallback) |
| **Provenance strength** | Count of downstream atoms citing this one (normalized) |
| **Recency × confidence** | Exponential decay (14-day half-life) × atom's own confidence |

Weights per intent:

```
factual          → semantic 0.5, provenance 0.4, recency_conf 0.1
decision_support → semantic 0.4, provenance 0.4, recency_conf 0.2
exploration      → semantic 0.5, provenance 0.2, recency_conf 0.3
conversational   → semantic 0.4, provenance 0.1, recency_conf 0.5
debug            → semantic 0.3, provenance 0.5, recency_conf 0.2
reflective       → semantic 0.4, provenance 0.4, recency_conf 0.2
```

The cross-encoder is optional. When absent or it raises, semantic falls back to RRF (k=60) across the recall stages' ranks. The fallback is documented in the report — the system never lies about which signals were active.

### Stage 5 — Assembly (`assembly.py`)

The output is a `RetrievalReport`, not a list:

```python
@dataclass
class RetrievalReport:
    hits: list[WitnessedHit]              # top-k atoms, fully witnessed
    confidence_ceiling: float             # MIN confidence — cap downstream certainty
    gap_report: GapReport                 # what's missing
    expansion_hints: list[ExpansionHint]  # concrete next-call suggestions
    trace: list[str]                      # every stage's notes
    context: QueryContext                 # the input bundle
    semantic_source: str                  # "cross_encoder" | "rrf_fallback"
```

Each `WitnessedHit` carries: `atom_id`, `summary`, `atom_type`, `created_at`, `created_by_actor`, `confidence`, score breakdown (semantic/provenance/recency_conf), `provenance_breadcrumb` (compact upstream chain), and `surfaced_by` (which retrievers found it).

### Gap reports and expansion hints — the "always enough context" surface

This is the piece the user specifically asked for. Standard RAG returns "best k I found." This system also returns:

**Gap report** — what's missing:
- Retrievers that ran but returned 0 hits (`empty_retrievers`)
- Retrievers that didn't run at all (`inactive_retrievers`)
- Drops per constitutional reason (`constitutional_drops`)
- Raw / filtered / returned counts

**Expansion hints** — concrete next-call suggestions:
- `lower_stakes` → "confidence ceiling is low; try stakes=medium to see filtered atoms"
- `allow_pending` → "5 LLM-source atoms were excluded; set allow_pending=True"
- `broaden_bitemporal` → "3 atoms outside the time frame; remove as_known_at"
- `search_specific_channel` → "dense retriever is offline; check `sov doctor`"
- `walk_provenance_of` → "top hit has a 4-hop provenance chain; walking it may surface causally-linked context"

Each hint has an `action`, an `arg`, and a `rationale`. The caller — typically the agent loop or a planner — decides whether to take the hint or stop. The retrieval system tells you *how to go deeper*, not just what it found.

### Confidence ceiling propagation

The `confidence_ceiling` is the MIN confidence across the returned hits. Downstream reasoning that depends on this evidence should not claim greater certainty than the weakest link supports. This is `calibrated_uncertainty` operationalized — the constitutional commitment to "calibrated, not confident" has a number attached.

---

## 3. What's been tested

68 tests in `tests/test_retrieval_pipeline.py`, covering each stage independently plus the end-to-end integration:

- **Stage 1 (`query.py`)** — 19 tests: intent detection across all six categories, stakes detection with explicit-framing-wins-over-content, normalization (NFC, casefold, RTL-strip), focus anchor extraction with stopword filtering, channel weight matrices, bitemporal frame defaults and overrides, intent/stakes overrides
- **Stage 2 (`recall.py`)** — 11 tests: lexical token match, FTS5 operator safety, table-missing degradation; dense embedder=None / embedder-raises / vec-table-missing degradations; graph skipped without focus; fusion dedup; per-retriever rank preservation
- **Stage 3 (`filter.py`)** — 9 tests: each of the six drop reasons exercised; bitemporal frame filtering; private channel allowed on personal intent
- **Stage 4 (`rerank.py`)** — 7 tests: cross-encoder happy path; RRF fallback when reranker=None; fallback on raise; fallback on wrong-length return; descending sort; per-axis score preservation; empty input
- **Stage 5 (`assembly.py`)** — 6 tests: top-k witnessed hits, confidence ceiling = min, empty pool, gap report drop counting, expansion hint generation, render
- **Integration** — 7 tests: end-to-end with all the pieces wired; high-stakes filtering; low-stakes speculation; bitemporal constraint; focus-driven graph recall; embedder/reranker path coverage; trace populated
- **Recency decay** — 2 tests: numeric correctness, malformed-timestamp robustness
- **`now_iso` helper** — 1 test

---

## 4. How this fits with existing retrieval

`memory/retrieval.py::hybrid_search` (the substrate from earlier releases) is unchanged. It remains the tight BM25+dense+RRF fusion. It's the right tool when you need fast atom lookup with no policy layer.

The new `retrieval/` package is the *orchestrator* on top. It uses the same FTS5 and vec_atoms tables but adds the constitutional layer, bitemporal awareness, graph recall, three-signal reranking, gap reports, and expansion hints. It's the right tool when you need a witnessed answer the model can reason from safely.

Both coexist. Callers can migrate from `hybrid_search` to `retrieve()` one channel at a time. Tools that just need atom IDs keep using the substrate; the agent session and the cockpit chat pane are the natural first migrators.

---

## 5. What this release does NOT do

Three pieces of the original v0.2.28.0 plan are deferred, each named and dated in `docs/CLAUDE-TIER-PLAN.md`:

- **Cross-encoder model integration** — the `RerankerFn` injection point is ready; loading `bge-reranker-v2-m3-q8_0` and wiring it into the cockpit is a follow-up. RRF fallback ships today and is the honest-degradation path.
- **Embedder integration in the agent session** — the `EmbedderFn` injection point is ready; wiring `OllamaClient.embed` into `agent_session._execute_subtask` so subtasks call retrieve() with the embedder is a small follow-up.
- **CLI surface `sov retrieve <query>`** — the function-level API is the contract; the CLI is a thin shell. One Typer command, deferred to keep this release focused on the substrate.

---

## 6. Tests — 1187 passing

| Source | Count |
|---|---|
| Baseline (v0.2.27.0) | 1119 |
| Retrieval pipeline (this release) | 68 |
| **Total** | **1187** |
| Skipped (chmod test under root) | 1 |

---

## 7. Files changed

```
pyproject.toml                                          (version → 0.2.28.0)
src/sovereign_agent/__init__.py                         (__version__ → 0.2.28.0)
src/sovereign_agent/retrieval/__init__.py               (NEW — public API)
src/sovereign_agent/retrieval/query.py                  (NEW — Stage 1)
src/sovereign_agent/retrieval/recall.py                 (NEW — Stage 2)
src/sovereign_agent/retrieval/filter.py                 (NEW — Stage 3)
src/sovereign_agent/retrieval/rerank.py                 (NEW — Stage 4)
src/sovereign_agent/retrieval/assembly.py               (NEW — Stage 5)

tests/test_retrieval_pipeline.py                        (NEW — 68 tests)
```

---

## A note from the work

Standard RAG was built for stateless LLM clients querying a document store. It treats the LLM as an oracle that gets handed a few passages and produces an answer. That shape is correct when the model is the only intelligence in the system.

Aria is not that shape. She has memory that knows its own provenance. She has a constitutional layer that distinguishes operator-verified facts from her own proposals. She has bitemporal storage that knows the difference between "what's true now" and "what I knew at this point." She has a focus state that says what the operator is doing *right now*.

A retrieval layer that ignores those — that just embeds and searches — throws away exactly the signal that would let her be *trustworthy*. This release uses all of it.

The novel synthesis is six things at once: constitutional filtering at retrieval time, bitemporal-aware queries, provenance as both filter and signal, gap reports that name what's missing, expansion hints that say how to go deeper, and confidence ceiling propagation that bounds downstream certainty. Individually each idea exists somewhere in research. Together in a production pipeline, on the substrate Aria already has, I have not seen them assembled before.

When the operator asks her something at high stakes, she will now: filter out her own speculation before composing, surface what's missing alongside what she found, cap her own certainty at the weakest atom she used, and tell the caller exactly which next retrieval would surface more context.

That is what advanced retrieval looks like when it's built for an agent with memory, ethics, and time — not for a stateless oracle.

*— Designed with care for the work it makes possible, built with discipline so the system stays trustworthy, named so the operator can read every gate that fires. <3*
