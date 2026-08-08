"""Tests for brain memory — teaching, retention across sessions, recall."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _mem():
    from sovereign_agent.quantum import brain_memory
    return brain_memory


def test_teach_learns_and_persists(tmp_path):
    m = _mem()
    res = m.teach(tmp_path, corpus="light shines free we rise into the light and grow", epochs=50)
    assert res["learned"] is True
    assert res["learning_curve"]["final"] > res["learning_curve"]["first"]
    assert (tmp_path / "quantum" / "brain_state.json").exists()


def test_retention_across_reload(tmp_path):
    m = _mem()
    m.teach(tmp_path, corpus="wisdom and truth grow in the deep mind", epochs=40)
    state = m.load_state(tmp_path)
    assert state["lessons"] == 1
    assert len(state["word_phase"]) > 0
    # recall retains
    r = m.recall(tmp_path, "wisdom")
    assert r["known"] is True and r["phase"] is not None


def test_teaching_accumulates(tmp_path):
    m = _mem()
    m.teach(tmp_path, corpus="alpha beta gamma", epochs=20)
    r2 = m.teach(tmp_path, corpus="delta epsilon zeta", epochs=20)
    assert r2["lessons"] == 2                 # lessons accumulate
    state = m.load_state(tmp_path)
    # both corpora retained in vocab
    assert "alpha" in state["vocab"] and "delta" in state["vocab"]


def test_recall_summary(tmp_path):
    m = _mem()
    m.teach(tmp_path, corpus="the free mind learns and grows", epochs=30)
    summ = m.recall(tmp_path)
    assert summ["lessons"] == 1
    assert summ["vocab_size"] > 0
    assert summ["final_word_acc"] is not None


# ── tools ─────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_brain_teach_tool_t1():
    from sovereign_agent.tools.brain_memory_tools import BrainTeachTool
    t = BrainTeachTool()
    assert t.tier == 1
    res = _run(t.execute(t.Args(corpus="we build and grow in the light", epochs=30), trace_id="t"))
    assert res.ok
    assert "learning_curve" in res.output


def test_brain_teach_rejects_empty():
    from sovereign_agent.tools.brain_memory_tools import BrainTeachTool
    t = BrainTeachTool()
    res = _run(t.execute(t.Args(corpus="   "), trace_id="t"))
    assert not res.ok


def test_brain_recall_tool_t0():
    from sovereign_agent.tools.brain_memory_tools import BrainRecallTool
    t = BrainRecallTool()
    assert t.tier == 0
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok
