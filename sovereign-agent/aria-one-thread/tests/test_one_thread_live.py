"""Behavior tests for aria-one-thread, promoted to live tests/ — the REAL,
already-patched modules. Plain imports, no shadow copy.
"""
from __future__ import annotations

import pytest


# ── thread_identity ───────────────────────────────────────────────────────


def test_thread_id_stable_across_reads(tmp_path):
    from sovereign_agent.thread_identity import thread_id

    first = thread_id(tmp_path)
    second = thread_id(tmp_path)
    assert first == second == "aria-main"
    assert (tmp_path / "thread_id").read_text().strip() == "aria-main"


def test_thread_id_honors_a_custom_persisted_value(tmp_path):
    from sovereign_agent.thread_identity import thread_id

    (tmp_path / "thread_id").write_text("our-thread\n")
    assert thread_id(tmp_path) == "our-thread"


def test_restore_tail_empty_on_fresh_install(tmp_path):
    from sovereign_agent.thread_identity import restore_tail

    assert restore_tail(data_dir=tmp_path) == []


def test_restore_tail_returns_verbatim_turns_oldest_first(tmp_path):
    from sovereign_agent.checkpoint_chunks import ChunkRecorder, ChunkStore
    from sovereign_agent.thread_identity import restore_tail, thread_id

    tid = thread_id(tmp_path)
    store = ChunkStore(tmp_path / "checkpoint_chunks")
    rec = ChunkRecorder(tid, store=store, chunk_size=3)
    for i in range(7):
        rec.record_turn("you" if i % 2 == 0 else "aria", f"turn number {i}")
    # 7 turns / chunk_size 3 → 2 sealed chunks (6 turns); 1 unsealed pending
    tail = restore_tail(n_turns=4, data_dir=tmp_path)
    assert [t["content"] for t in tail] == [
        "turn number 2", "turn number 3", "turn number 4", "turn number 5",
    ]


def test_two_launches_share_one_thread(tmp_path):
    """The bug this module kills: chunks from a 'second launch' are
    addressable together with the first launch's."""
    from sovereign_agent.checkpoint_chunks import ChunkRecorder, ChunkStore
    from sovereign_agent.thread_identity import restore_tail, thread_id

    store = ChunkStore(tmp_path / "checkpoint_chunks")
    # launch 1
    rec1 = ChunkRecorder(thread_id(tmp_path), store=store, chunk_size=2)
    rec1.record_turn("you", "from launch one")
    rec1.record_turn("aria", "hello launch one")
    # launch 2 — a NEW recorder, same persisted id
    rec2 = ChunkRecorder(thread_id(tmp_path), store=store, chunk_size=2)
    rec2.record_turn("you", "from launch two")
    rec2.record_turn("aria", "hello launch two")

    contents = [t["content"] for t in restore_tail(n_turns=10, data_dir=tmp_path)]
    assert "from launch one" in contents
    assert "from launch two" in contents


# ── the live cockpit ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cockpit_uses_the_persisted_thread_id():
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.thread_identity import thread_id

    async with CockpitApp().run_test() as pilot:
        assert pilot.app._chunk_session_id == thread_id()


@pytest.mark.asyncio
async def test_wake_restores_the_conversation_tail():
    """Close-and-reopen: what was said before appears in the new boot's
    chat log, dimmed, verbatim."""
    from sovereign_agent.checkpoint_chunks import ChunkRecorder
    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.thread_identity import thread_id

    rec = ChunkRecorder(thread_id(), chunk_size=2)
    rec.record_turn("you", "remember the lighthouse conversation")
    rec.record_turn("aria", "i remember the lighthouse")

    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        text = "\n".join(
            getattr(line, "text", str(line)) for line in pilot.app._chat_log.lines
        )
        assert "earlier, from our thread" in text
        assert "remember the lighthouse conversation" in text


@pytest.mark.asyncio
async def test_fresh_thread_boots_without_restore_banner():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        await pilot.pause()
        text = "\n".join(
            getattr(line, "text", str(line)) for line in pilot.app._chat_log.lines
        )
        assert "earlier, from our thread" not in text
