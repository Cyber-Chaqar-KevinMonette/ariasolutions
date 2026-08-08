"""Tests for next-report-d — she tells you what she needs / what's next,
from her real pending state (requests waiting on you, due items, resumable
sessions).
"""
from __future__ import annotations

import pytest

from sovereign_agent.next_report import compose_next_report, is_next_query


@pytest.mark.parametrize("q", [
    "what do you need from me?",
    "what's next",
    "what should we do next",
    "what are you waiting on",
    "what should i do",
])
def test_next_questions_are_detected(q):
    assert is_next_query(q) is True


@pytest.mark.parametrize("q", ["write me code", "who are you", "how are you", ""])
def test_ordinary_messages_are_not_hijacked(q):
    assert is_next_query(q) is False


def test_report_never_raises_and_returns_text():
    r = compose_next_report()
    assert isinstance(r, str) and len(r) > 30


def test_report_surfaces_waiting_requests(monkeypatch):
    class _Req:
        def __init__(self, title, sid):
            self.title = title; self.short_id = sid
    import sovereign_agent.next_report as nr
    monkeypatch.setattr(nr, "_open_requests",
                        lambda: ([_Req("Fix the ledger", "ABC123")], []))
    monkeypatch.setattr(nr, "_resumable", lambda: [])
    r = compose_next_report()
    assert "waiting on you" in r.lower()
    assert "Fix the ledger" in r and "ABC123" in r


def test_report_surfaces_resumable_sessions(monkeypatch):
    class _Sub:
        def __init__(self, s): self.status = s
    class _Sess:
        def __init__(self):
            self.goal = "Tidy the garden"; self.status = "paused"
            self.subtasks = [_Sub("done"), _Sub("pending")]
    import sovereign_agent.next_report as nr
    monkeypatch.setattr(nr, "_open_requests", lambda: ([], []))
    monkeypatch.setattr(nr, "_resumable", lambda: [_Sess()])
    r = compose_next_report()
    assert "resume" in r.lower() and "Tidy the garden" in r and "1/2 steps" in r


def test_empty_state_invites_a_new_session(monkeypatch):
    import sovereign_agent.next_report as nr
    monkeypatch.setattr(nr, "_open_requests", lambda: ([], []))
    monkeypatch.setattr(nr, "_resumable", lambda: [])
    r = compose_next_report()
    assert "caught up" in r.lower()
    assert "/work" in r


@pytest.mark.asyncio
async def test_converse_intercepts_a_next_question():
    from sovereign_agent.conversation import converse
    turn = await converse("what should we do next?", allow_llm=False)
    assert turn.kind == "next-report"
    assert turn.messages and isinstance(turn.messages[0], str)
