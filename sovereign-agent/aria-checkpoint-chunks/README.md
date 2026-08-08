# aria-checkpoint-chunks — Workstream P: god-tier conversation checkpoint chunks (anti-compression)

**Kevin's ask (paraphrased):** design a system where Aria saves conversation segments as addressable
"god-tier chunks/checkpoints" she can call on when she determines she needs them — so that lossy
compression is needed *significantly less often* than typical AI systems require. She can still
compress whenever she wants; the point is she shouldn't *have to*, because full-fidelity detail
stays reachable another way.

## What this composes (not a new subsystem)

- **`ChunkStore`** (`checkpoint_chunks/store.py`) — append-only NDJSON, atomic writes, mirrors
  `ApplyQueueStore`'s and `EpistemicLedger`'s exact idiom (Workstreams C/H3). Seals bounded spans of
  raw turns verbatim — sealing is the *non-lossy* analog of compressing: nothing is condensed, it's
  just moved into an addressable record.
- **`ChunkIndex`** (`checkpoint_chunks/index.py`) — generalizes `palace.py`'s Closet pattern
  (topic → pointer list) into topic/keyword → chunk_id lookup. Deliberately self-contained (no
  dependency on Palace's SQLite Room/Entity/Triple machinery) so chunk storage stays lightweight.
- **`ChunkRecorder`** (`checkpoint_chunks/recorder.py`) — buffers live turns, auto-seals every 20
  (configurable), or on explicit `seal_now()`.
- **`RecallChunkTool`** (`tools/recall_chunk_tool.py`, Tier 0) — modeled on `RetrieveMemoryTool`'s
  existing tool-exposure shape. Given a keyword, returns the **verbatim** original chunk text, never
  a summary.
- **Compression oracle retune** (`loop.py`'s `COMPRESSION ORACLE` system-prompt section) — now tells
  the model to try `recall_chunk(keyword)` before `compress_context()`. Compression remains fully
  available on request (Kevin was explicit about this) — it's the second resort now, not the default.
- **Wiring** (`cockpit/app.py`'s `_record()`) — every chat line that already flows through this method
  (both `_write_you`/`_write_aria`'s calls, and `meta` lines) also feeds a `ChunkRecorder`, lazily
  built per cockpit launch. Best-effort, matches the existing disk-transcript write's own
  try/except discipline — a chunk-write failure never blocks the cockpit's UI flow.

## Why this integration point, not `agent_session.run_session()`

The original design considered wiring into `loop.py`'s tool-calling agent loop directly. Investigation
(done as part of Workstream N) found `run_session()` has **zero live call sites** — it's a real,
separate, pre-existing gap (folded into K/F), not a place to hang new behavior on top of right now.
The cockpit's `_record()` method is the actual, already-wired, low-risk integration point: every real
conversational turn Kevin has with Aria already flows through it (it's what feeds the on-disk
transcript file today) — chunking there means the mechanism works for the surface Kevin actually asked
about ("conversation segments") without touching the higher-stakes tool-calling loop.

## Tests (17/17 passing pre-apply)

`tests/test_patcher.py` — all 3 patches (tools/__init__.py, loop.py, cockpit/app.py) apply cleanly
against the CURRENT live files, are idempotent, and the patched result compiles.
`tests/test_checkpoint_chunks.py` — a sealed chunk round-trips its raw turns byte-for-byte; a
freshly-created store correctly scopes `all_chunks()` by session; `ChunkRecorder` auto-seals at the
configured size and flushes a partial buffer on demand; `ChunkIndex`'s keyword/topic lookup finds real
matches and stays quiet on a clean miss (D's own precision discipline); `RecallChunkTool` returns full
original text (verified via string containment, not a truncated/altered form) and an empty result on
no match. **Capstone test**: a specific detail mentioned once early in a 200-turn synthetic session is
still retrievable byte-for-byte via `recall_chunk` — the honest, grounded version of "less compression
needed" (whether `compress_context()` actually gets called is the model's decision, driven by the
retuned oracle hint — not something a unit test can force without a real LLM in the loop; what IS
directly provable is that full fidelity survives arbitrarily far into a long session without ever
being compressed away, which is the actual mechanism that reduces the *need* to compress).

Reversible: restore the 3 backed-up files, `rm -r src/sovereign_agent/checkpoint_chunks/
src/sovereign_agent/tools/recall_chunk_tool.py`.
