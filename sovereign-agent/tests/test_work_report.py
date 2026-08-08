"""Tests for work-report-d — she tells you what she did (from her real
review journal / session history), and how to inspect it.
"""
from __future__ import annotations

import pytest

from sovereign_agent.review_journal import build_review
from sovereign_agent.work_report import compose_work_report, is_work_query


# ── detection ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    "what did you do?",
    "what have you worked on?",
    "show me your work",
    "what did you get done today",
    "what have you been working on",
])
def test_work_questions_are_detected(q):
    assert is_work_query(q) is True


@pytest.mark.parametrize("q", ["what's the weather", "who are you", "help me code", ""])
def test_ordinary_messages_are_not_hijacked(q):
    assert is_work_query(q) is False


# ── composed report reads the real review journal ───────────────────────
def _seed_review(data_dir, session_id="sess-1", goal="Tidy the garden", status="complete"):
    build_review({
        "session_id": session_id, "goal": goal, "mode": "work", "status": status,
        "created_at": "t", "updated_at": "2026-07-12T10:00:00Z",
        "subtasks": [
            {"id": "a", "description": "step one", "status": "done", "required_tier": 1},
            {"id": "b", "description": "step two", "status": "done", "required_tier": 1},
        ],
    }, data_dir=data_dir)


def test_report_summarizes_recent_reviews(tmp_path):
    _seed_review(tmp_path, "sess-1", "Tidy the garden")
    _seed_review(tmp_path, "sess-2", "Fix the ledger")
    r = compose_work_report(tmp_path)
    assert "Tidy the garden" in r and "Fix the ledger" in r
    assert "/review" in r                       # tells you how to inspect
    assert "2/2 steps" in r                      # real progress from plan.json


def test_report_points_to_the_index_and_readme(tmp_path):
    _seed_review(tmp_path)
    r = compose_work_report(tmp_path)
    assert "INDEX.md" in r and "README.md" in r


def test_empty_state_invites_a_work_session(tmp_path):
    r = compose_work_report(tmp_path)   # no reviews, no sessions
    assert "/work" in r
    assert "haven't run any work sessions" in r.lower() or "recent work sessions" in r.lower()


# ── converse() routes a work question to the real report ────────────────
@pytest.mark.asyncio
async def test_converse_intercepts_a_work_question():
    from sovereign_agent.conversation import converse
    turn = await converse("what did you do?", allow_llm=False)
    assert turn.kind == "work-report"
    assert turn.messages and isinstance(turn.messages[0], str)
