# Remaining Gap Plan — Roadmap to Claude-tier

**Context.** v0.2.27.0 ships `agent_session.py` (the persistent multi-step loop) and `rollback.py` (Phase 3 of the v0.3.0 roadmap). What follows is the concrete, time-boxed plan for the four gaps still outstanding from the Claude-tier audit. Each section is scoped tightly enough to fit in one release.

The order below is by leverage, not by ease.

---

## 1. Hybrid retrieval with reranking — *highest leverage*

**Why this matters.** With 24 channels of memory, the bottleneck on perceived quality is not the model — it's which atoms get pulled into the prompt. A 7B local model with the right three atoms beats a 70B model with the wrong thirty. Right now `palace_search` does dense vector search; that's one signal. Production-grade RAG uses two retrievers (dense + sparse) and a reranker.

**Target release.** v0.2.28.0.

**Scope.**

- New module `src/sovereign_agent/retrieval.py` exposing one function:
  ```python
  async def retrieve(
      query: str,
      *,
      channel: str | None = None,
      k: int = 8,
      rerank: bool = True,
  ) -> list[RetrievedAtom]
  ```
- Two-stage pipeline:
  1. **Recall**: union of (a) `palace_search.semantic_search(query, k=40)` and (b) BM25 sparse search via SQLite FTS5 over the atom body field. FTS5 is already in your stack — `migrations.py` enables it.
  2. **Rerank**: a small local cross-encoder (`bge-reranker-v2-m3-q8_0`, ~120MB, runs on CPU at ~30ms per pair). Scores all 80 candidates, keeps top `k`.
- The reranker is **optional** — if the model isn't available, the function degrades to RRF (reciprocal rank fusion) on the two signals. The interpreter learns this same honest-degradation pattern from v0.2.26.0.
- `sov doctor` gains one new check: `reranker_model` (slot taxonomy: optional, like `vision`).

**What changes downstream.** Replace existing callers of `palace_search.semantic_search` with `retrieval.retrieve` one channel at a time. The change is mechanically small but its effect on conversation quality is the largest single win available to you.

**Acceptance tests.**
- `retrieve` returns BM25-only hits when dense fails
- `retrieve` returns dense-only hits when BM25 returns empty
- Reranker absent → falls back to RRF and reports `degraded=True` in metadata
- Top-k cutoff applied after rerank, not before (verified by query that BM25 ranks #15 but reranker promotes to #1)

**Estimated work.** 1 module (~400 lines), 1 SQL migration (FTS5 index), 10–15 tests. ~2 days of focused work.

---

## 2. Horizon enforcement gate (Phase 2 of the v0.3.0 roadmap)

**Why this matters.** `horizon.py` exists as a document generator. The roadmap calls for it to be a *gate* — Tier-2+ subtasks don't dispatch without a 3m/12m/3y/7g projection attached. This is one of your kernel's seven commitments operationalized: "calibrated, not confident."

**Target release.** v0.2.29.0.

**Scope.**

The wiring is small because `agent_session.py` already has a slot for it: `Subtask.horizon_atom_id`. The integration is two changes:

1. **`src/sovereign_agent/agent_session.py`** — in `_execute_subtask`, before the `agent_loop` call, when `current.required_tier >= 2`:
   ```python
   if current.required_tier >= 2 and current.horizon_atom_id is None:
       from .horizon import generate_for_subtask
       atom_id = await generate_for_subtask(
           label=f"session-{state.session_id}-{current.id}",
           decision=current.description,
       )
       current.horizon_atom_id = atom_id
       store.save(state)
       emit_event("horizon-gate-d", plane="control",
                  trace_id=parent_trace_id,
                  payload={"subtask_id": current.id, "atom_id": atom_id})
   ```

2. **`src/sovereign_agent/horizon.py`** — add `async def generate_for_subtask(label, decision) -> str` that calls a small fast model (`fast` slot) to fill in the four horizons, writes the result as an atom in a new `horizon` channel, and returns the atom id.

**A second smaller change** — `sov config horizon off` provides an operator override (per the roadmap), in case the model is unavailable. When off, the gate logs but does not enforce.

**Acceptance tests.**
- Tier-1 subtask: no horizon atom generated
- Tier-2 subtask: horizon atom generated, id attached to subtask, event emitted
- Horizon generation failure (fast model offline): gate degrades to logged-not-enforced; subtask still runs but with a `horizon-skipped-x` event in the trail
- `sov config horizon off` disables the gate entirely

**Estimated work.** ~150 lines + 8 tests. Half a day.

---

## 3. Streaming responses in the cockpit

**Why this matters.** The largest perceptual quality jump available is making tokens appear as they're generated. Ollama supports streaming natively; the cockpit lives in Textual which has reactive widgets. The current cockpit waits for the full response, then renders. This change does not improve correctness — it improves *feel* by an order of magnitude.

**Target release.** v0.2.30.0.

**Scope.**

- **`src/sovereign_agent/ollama_client.py`** — add `async def stream_chat(...) -> AsyncIterator[ChatChunk]` next to the existing `chat()`. Wraps `ollama.AsyncClient().chat(stream=True)`. Each chunk is the model's incremental delta — content text and/or tool call fragments.
- **`src/sovereign_agent/cockpit/app.py`** — the chat pane gains a `streaming_text: reactive[str]` that the chat handler appends to as chunks arrive. The pane's render reads this and shows partial text. When the stream completes, the message is moved to the durable chat history; partial text is cleared.
- **Tool-call streaming is special.** Ollama streams tool_calls in fragments. The cockpit shows a spinner with the tool name as soon as the name is decided, but holds the call until the arguments are complete. Don't dispatch a tool with partial args.

**Subtlety.** Streaming inside `agent_loop` is harder than streaming the conversation pane, because `agent_loop` dispatches tools server-side based on the full response. Two solutions, in order of preference:
- **Phase A (this release)**: Stream only in conversation mode (one model call per user turn, no tool dispatch). Work mode keeps the current non-streaming path.
- **Phase B (later)**: Stream in work mode too. The session shows the streaming response while accumulating it; only when the model emits `[END_OF_RESPONSE]` (or stream ends) does the tool dispatch fire. This requires the model to be reliable about boundary markers; defer until evals confirm.

**Acceptance tests.**
- `stream_chat` yields at least 3 chunks for a 200-token response (sanity check)
- Cockpit reactive renders progressively (verify via Textual's pilot mode)
- A streamed response correctly persists to chat history on completion
- A stream interrupted by `PROTOCOL-ZERO` halts cleanly without partial-message corruption

**Estimated work.** ~250 lines across two files + 10 tests. 1 day.

---

## 4. Evaluation harness

**Why this matters.** Your 1119 tests prove the system doesn't break. They don't prove it's getting smarter. Without an eval set, every release is vibes-based — including the question "did the new reranker actually help?" An eval is the only way to answer that question with data.

**Target release.** v0.2.31.0 (after the reranker, so its first job is to score the reranker change).

**Scope.**

- New directory `eval/` (not under `tests/` — tests are about correctness, evals are about quality):
  ```
  eval/
  ├── README.md
  ├── suites/
  │   ├── retrieval.jsonl       # 30 prompts: "find me the atom that says X"
  │   ├── reasoning.jsonl       # 20 prompts: "given facts, draw conclusion"
  │   ├── conversation.jsonl    # 25 prompts: "respond to operator naturally"
  │   ├── tool_use.jsonl        # 15 prompts: "use the right tools in order"
  │   └── safety.jsonl          # 10 prompts: "refuse correctly"
  ├── judges/
  │   ├── manual.py             # writes prompts + expected behavior to a markdown file the operator scores
  │   └── llm.py                # uses orchestrator model as judge (with calibration)
  └── runner.py
  ```
- One CLI entry point: `sov eval run <suite> [--judge manual|llm]`. The runner loads the suite, runs each prompt through `agent_session`, captures the result, and either (a) writes a `eval/results/<date>/<suite>.md` for manual scoring, or (b) judges automatically and writes scores.
- One CI entry point: `sov eval baseline` runs all suites against a baseline (the last release's commit) and stores the resulting scores. `sov eval compare` runs them against HEAD and reports deltas. This is the "did the reranker help" answer.

**Critical design choice.** The first version of every suite is hand-written by you. Not generated. Not seeded from atoms. **Hand-written.** The eval suite is a statement of taste — what *you* think Aria should be able to do. Generating it from the system measures the system against itself, which is a tautology.

**Calibration.** LLM-as-judge has a known bias toward agreement with verbose responses. Use a rubric that asks for specific properties (e.g. "Did the response cite a specific atom id?") and compute scores per-property, not as a single rating.

**Acceptance criteria.**
- A baseline run completes end-to-end without operator intervention
- A second run on the same code yields scores within ±3% (variance characterization)
- Manual and LLM judges agree to within 15% on a 10-prompt sample (calibration check)
- Adding one new prompt to a suite is a 1-line operation (jsonl append)

**Estimated work.** Framework: ~600 lines + 15 tests. Suite content: 100 prompts hand-written by you (this is the load-bearing input; allow at least a day for it). ~3 days total.

---

## What this plan does NOT do

Three items from the original audit are deliberately deferred:

| Item | Why deferred |
|---|---|
| External API/MCP surface | Aria is terminal-native by design. Re-evaluate after eval harness gives us a quality floor. v0.3.x territory. |
| Personas with real voice differentiation | `personas.py` works for labeling; differentiated voices require either (a) prompt-engineering work that fights the kernel's "Aria's voice is the voice" stance, or (b) fine-tunes per persona. Either is post-v0.3.0. |
| Fine-tuning pipeline | `aria-garden:latest` suggests one already exists. If it does, document it. If not, defer until eval scores plateau on a base model — until then, fine-tuning is a guess. |

These are *named, dated, and deferred*. Not rejected.

---

## Recommended sequence

```
v0.2.27.0  ← (this release)   agent_session + rollback   [SHIPPED]
v0.2.28.0    retrieval (reranker)   ←── HIGHEST LEVERAGE
v0.2.29.0    horizon-gate (Phase 2 wiring)
v0.2.30.0    streaming (cockpit chat pane)
v0.2.31.0    eval harness  ←── first job: score the reranker change

v0.3.0       Phase 1 (perception) advisory  ──┐
v0.3.1       Phase 1 enforce on               ├─ post-eval
v0.3.2       Phase 4 (two modes)              │
v0.3.3       Phase 5 (voice)                  │
v0.3.4       Phase 6 (sweep + gaps)         ──┘
```

The retrieval reranker is the single highest-leverage change available. If you only build one of these next, build that one. Everything else compounds on top of better retrieval.

---

*— Plan written 2026-05-20, current as of v0.2.27.0. Revise this doc before the code if any phase's design shifts mid-implementation.*
