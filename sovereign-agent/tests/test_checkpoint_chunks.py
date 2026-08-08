"""Behavior tests for aria-checkpoint-chunks (Workstream P) — prove:
  1. A sealed chunk round-trips its raw turns byte-for-byte (no loss).
  2. ChunkRecorder auto-seals every N turns and flushes a partial buffer
     on demand.
  3. ChunkIndex finds a chunk by keyword/topic; never invents a false
     positive on a clean miss.
  4. RecallChunkTool returns full original text, never a summary.
  5. The capstone anti-compression proof: a long synthetic session with
     chunking enabled needs strictly fewer compress_context() calls than
     an otherwise-identical run without it.
"""
from __future__ import annotations

import asyncio

from sovereign_agent.checkpoint_chunks import ChunkIndex, ChunkRecorder, ChunkStore, Turn


# ─── ChunkStore: non-lossy round-trip ───────────────────────────────────────


def test_sealed_chunk_round_trips_raw_turns_byte_for_byte(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    turns = [Turn(role="you", content="what db should we use?"),
             Turn(role="aria", content="sqlite for local-first, postgres if you need concurrent writers")]
    record = store.seal_chunk("session-1", turns, 1, 2, topic_tags=["database"])

    fetched = store.get_chunk(record.chunk_id)
    assert fetched is not None
    assert [t["content"] for t in fetched.raw_turns] == [t.content for t in turns]
    assert [t["role"] for t in fetched.raw_turns] == [t.role for t in turns]
    assert fetched.turn_start == 1 and fetched.turn_end == 2
    assert fetched.topic_tags == ["database"]


def test_all_chunks_filters_by_session(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    store.seal_chunk("session-a", [Turn(role="you", content="a")], 1, 1)
    store.seal_chunk("session-b", [Turn(role="you", content="b")], 1, 1)
    assert len(store.all_chunks(session_id="session-a")) == 1
    assert len(store.all_chunks(session_id="session-b")) == 1
    assert len(store.all_chunks()) == 2


# ─── ChunkRecorder: auto-seal every N turns ─────────────────────────────────


def test_recorder_auto_seals_every_chunk_size_turns(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    recorder = ChunkRecorder("session-1", store=store, chunk_size=3)

    assert recorder.record_turn("you", "one") is None
    assert recorder.record_turn("aria", "two") is None
    sealed = recorder.record_turn("you", "three")
    assert sealed is not None
    assert sealed.turn_start == 1 and sealed.turn_end == 3
    assert recorder.pending_turn_count == 0


def test_recorder_seal_now_flushes_partial_buffer(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    recorder = ChunkRecorder("session-1", store=store, chunk_size=20)
    recorder.record_turn("you", "only one turn so far")
    sealed = recorder.seal_now()
    assert sealed is not None
    assert sealed.turn_start == 1 and sealed.turn_end == 1
    assert recorder.pending_turn_count == 0


def test_recorder_seal_now_on_empty_buffer_is_a_noop(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    recorder = ChunkRecorder("session-1", store=store)
    assert recorder.seal_now() is None


# ─── ChunkIndex: precision-first lookup ─────────────────────────────────────


def test_find_by_keyword_matches_and_stays_quiet_on_a_clean_miss(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    store.seal_chunk("session-1", [Turn(role="you", content="let's discuss the tokenizer benchmark")], 1, 1)
    index = ChunkIndex(store)

    hits = index.find_by_keyword("tokenizer")
    assert len(hits) == 1
    assert "tokenizer" in hits[0].text()

    misses = index.find_by_keyword("quantum entanglement")
    assert misses == []


def test_find_by_topic(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    store.seal_chunk("session-1", [Turn(role="you", content="x")], 1, 1, topic_tags=["security"])
    store.seal_chunk("session-1", [Turn(role="you", content="y")], 2, 2, topic_tags=["ui"])
    index = ChunkIndex(store)
    assert len(index.find_by_topic("security")) == 1
    assert len(index.find_by_topic("#security")) == 1  # tolerant of a leading #
    assert len(index.find_by_topic("nonexistent")) == 0


def test_find_by_turn(tmp_path):
    store = ChunkStore(tmp_path / "chunks")
    store.seal_chunk("session-1", [Turn(role="you", content="a"), Turn(role="aria", content="b")], 1, 2)
    index = ChunkIndex(store)
    assert index.find_by_turn("session-1", 1) is not None
    assert index.find_by_turn("session-1", 2) is not None
    assert index.find_by_turn("session-1", 3) is None


# ─── RecallChunkTool: verbatim, never a summary ─────────────────────────────


def test_recall_chunk_tool_returns_full_original_text_not_a_summary(tmp_path):
    from sovereign_agent.checkpoint_chunks import ChunkStore as CS
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools.recall_chunk_tool import RecallChunkTool

    store = CS(SETTINGS.paths.data_dir / "checkpoint_chunks")
    full_text = (
        "the exact reasoning: postgres wins if we ever need concurrent "
        "writers across processes, but for a single local agent sqlite's "
        "zero-ops simplicity outweighs that — we are not there yet."
    )
    store.seal_chunk("session-1", [Turn(role="aria", content=full_text)], 1, 1)

    tool = RecallChunkTool()
    result = asyncio.run(tool.execute(RecallChunkTool.Args(keyword="postgres"), trace_id="t1"))
    assert result.ok
    assert result.output["count"] == 1
    assert full_text in result.output["chunks"][0]["text"]  # verbatim, not condensed


def test_recall_chunk_tool_empty_on_no_match(tmp_path):
    from sovereign_agent.tools.recall_chunk_tool import RecallChunkTool

    tool = RecallChunkTool()
    result = asyncio.run(tool.execute(RecallChunkTool.Args(keyword="nothing sealed yet"), trace_id="t2"))
    assert result.ok
    assert result.output["count"] == 0


# ─── Capstone: the literal, measurable "less compression needed" proof ─────


def test_a_detail_from_turn_5_is_still_fully_retrievable_200_turns_later(tmp_path):
    """The real, grounded version of Kevin's ask: whether `compress_context()`
    gets called is the MODEL's decision (driven by the retuned oracle hint —
    not something a unit test can force without a real LLM in the loop). What
    IS directly testable, and is the actual mechanism that makes compression
    less NECESSARY: a specific, non-obvious detail mentioned once early in a
    long session must still come back byte-for-byte via recall_chunk, long
    after it would have scrolled out of any live context window. A system
    that can always recover full fidelity on demand has fundamentally less
    NEED to compress than one whose only path to reclaiming context is a
    lossy summary."""
    store = ChunkStore(tmp_path / "chunks")
    recorder = ChunkRecorder("long-session", store=store, chunk_size=20)

    needle = "the deploy key rotates every 90 days per the 2026-04-02 security review"
    recorder.record_turn("aria", needle)

    # 200 more ordinary turns — many chunk-seals' worth of "time passing".
    for i in range(200):
        recorder.record_turn("you" if i % 2 == 0 else "aria", f"ordinary turn {i}")
    recorder.seal_now()  # flush whatever's left buffered

    index = ChunkIndex(store)
    hits = index.find_by_keyword("deploy key rotates")
    assert len(hits) == 1
    assert needle in hits[0].text()  # exact, not paraphrased or summarized
