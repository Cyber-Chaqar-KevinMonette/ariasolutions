"""Behavior tests for aria-continual-learning, promoted to live tests/ —
tests the REAL, already-patched `sovereign_agent.aria_lm.data` /
`sovereign_agent.aria_lm.retrain_trigger` /
`sovereign_agent.tools.continual_learning_tools` directly, no shadow copy,
no `sys.modules` manipulation. See test_continual_learning.py (staged
only) for the shadow-copy pre-apply verification version.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from ulid import ULID


def _write_lesson(conn, *, trigger="t", context="c", rule="always write under sandbox dir",
                   correction="use sandbox path", failure_mode=None, confidence=0.8):
    conn.execute(
        "INSERT INTO lessons "
        "(lesson_id, ts, trigger, context, failure_mode, correction, rule, evidence_refs, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(ULID()),
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            trigger, context, failure_mode, correction, rule,
            json.dumps([]), confidence,
        ),
    )
    conn.commit()


def test_gather_corpus_degrades_gracefully_with_no_lessons():
    from sovereign_agent.aria_lm.data import gather_corpus

    corpus = gather_corpus(max_chars=50000)
    assert isinstance(corpus, str) and len(corpus) > 100


def test_gather_corpus_includes_real_lesson_text_when_lessons_exist():
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.data import gather_corpus

    conn = _db.open_atoms_db()
    try:
        _write_lesson(
            conn,
            trigger="wrote-outside-sandbox-live",
            rule="always write under sandbox dir (live)",
            correction="use the sandbox-scoped path helper (live)",
        )
    finally:
        conn.close()

    corpus = gather_corpus(max_chars=50000, clean=False)
    assert "always write under sandbox dir (live)" in corpus


def test_gather_lesson_text_never_raises_on_missing_db(monkeypatch):
    from sovereign_agent.aria_lm import retrain_trigger

    def _boom():
        raise RuntimeError("no db here")

    monkeypatch.setattr(retrain_trigger, "_open_db", _boom)
    assert retrain_trigger.gather_lesson_text() == ""
    assert retrain_trigger.total_lesson_count() == 0


def test_check_retrain_proposal_none_when_below_threshold(tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.retrain_trigger import check_retrain_proposal

    conn = _db.open_atoms_db()
    try:
        for _ in range(5):
            _write_lesson(conn)
    finally:
        conn.close()

    assert check_retrain_proposal(tmp_path / "data", threshold=20) is None


def test_check_retrain_proposal_fires_once_threshold_reached(tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.retrain_trigger import check_retrain_proposal

    conn = _db.open_atoms_db()
    try:
        for _ in range(21):
            _write_lesson(conn)
    finally:
        conn.close()

    proposal = check_retrain_proposal(tmp_path / "data", threshold=20)
    assert proposal is not None
    assert proposal["due"] is True
    assert proposal["new_lessons_since_last_retrain"] == 21
    assert proposal["suggested_command"] == "python -m sovereign_agent.aria_lm.pipeline"


def test_record_retrain_resets_the_baseline(tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.retrain_trigger import (
        check_retrain_proposal, record_retrain, total_lesson_count,
    )

    conn = _db.open_atoms_db()
    try:
        for _ in range(25):
            _write_lesson(conn)
    finally:
        conn.close()

    data_dir = tmp_path / "data"
    assert check_retrain_proposal(data_dir, threshold=20) is not None

    record_retrain(data_dir)
    assert check_retrain_proposal(data_dir, threshold=20) is None

    conn = _db.open_atoms_db()
    try:
        for _ in range(3):
            _write_lesson(conn)
    finally:
        conn.close()
    assert check_retrain_proposal(data_dir, threshold=20) is None
    assert total_lesson_count() == 28


@pytest.mark.asyncio
async def test_propose_retrain_tool_never_calls_grow_mind(monkeypatch):
    from sovereign_agent.tools.continual_learning_tools import ProposeRetrainTool

    def _must_not_be_called(*a, **kw):
        raise AssertionError("propose_retrain must never call grow_mind()")

    import sovereign_agent.aria_lm.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "grow_mind", _must_not_be_called)

    tool = ProposeRetrainTool()
    result = await tool.execute(tool.Args(threshold=1), trace_id="t1")
    assert result.ok


def test_propose_retrain_tool_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY

    assert "propose_retrain" in _TIER_REGISTRY
    assert _TIER_REGISTRY["propose_retrain"].tier == 1


@pytest.mark.asyncio
async def test_propose_retrain_tool_reports_due_false_when_no_lessons():
    from sovereign_agent.tools.continual_learning_tools import ProposeRetrainTool

    tool = ProposeRetrainTool()
    result = await tool.execute(tool.Args(threshold=20), trace_id="t2")
    assert result.ok
    assert result.output["due"] is False
