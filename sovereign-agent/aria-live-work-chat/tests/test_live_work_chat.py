"""Behavior tests for aria-dual-inbox (Workstream O) — prove:
  1. Old rows with no `direction` column still read as `to_human` (migration
     safety — every request ever filed before this field existed keeps its
     original meaning exactly).
  2. `SendToHumanTool` files a request that shows up ONLY in the to_human
     list, never in to_aria.
  3. `sov requests tell`-equivalent (`RequestStore.tell_aria`) files a note
     that shows up ONLY in to_aria, never to_human.
  4. `ReadInboxTool` returns only open to_aria items.
  5. `list_open`/`list`/`open_count` direction filters behave correctly.
"""
from __future__ import annotations

import asyncio

import pytest

from sovereign_agent.persistence.store import ErebloStore
from sovereign_agent.workflow.requests import (
    DIRECTION_TO_ARIA,
    DIRECTION_TO_HUMAN,
    RequestStore,
)


@pytest.fixture
def store(tmp_path) -> RequestStore:
    return RequestStore(ErebloStore(tmp_path / "atoms.db"))


# ─── migration safety ───────────────────────────────────────────────────────


def test_direction_defaults_to_to_human_for_a_freshly_opened_request(store):
    req = store.open("note", "a plain old request")
    assert req.direction == DIRECTION_TO_HUMAN


def test_a_pre_migration_row_reads_as_to_human(store, tmp_path):
    """Simulate a row written before the `direction` column existed: insert
    directly without it, bypassing the dataclass default, and confirm the
    reader still resolves it to to_human (not an empty/null direction)."""
    raw_store = ErebloStore(tmp_path / "atoms.db")
    raw_store.execute(
        "INSERT INTO human_requests(request_id, kind, title, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("legacy-row-1", "note", "a request from before direction existed", "2020-01-01T00:00:00+00:00"),
    )
    legacy_store = RequestStore(raw_store)
    req = legacy_store.get("legacy-row-1")
    assert req is not None
    assert req.direction == DIRECTION_TO_HUMAN


# ─── direction separation ───────────────────────────────────────────────────


def test_send_to_human_shows_up_only_in_to_human(store):
    req = store.send_to_human("ask Kevin something")
    assert req.direction == DIRECTION_TO_HUMAN
    to_human = [r.request_id for r in store.list_open(direction=DIRECTION_TO_HUMAN)]
    to_aria = [r.request_id for r in store.list_open(direction=DIRECTION_TO_ARIA)]
    assert req.request_id in to_human
    assert req.request_id not in to_aria


def test_tell_aria_shows_up_only_in_to_aria(store):
    req = store.tell_aria("remember to check the logs")
    assert req.direction == DIRECTION_TO_ARIA
    to_human = [r.request_id for r in store.list_open(direction=DIRECTION_TO_HUMAN)]
    to_aria = [r.request_id for r in store.list_open(direction=DIRECTION_TO_ARIA)]
    assert req.request_id in to_aria
    assert req.request_id not in to_human


def test_list_for_aria_matches_list_open_to_aria(store):
    store.tell_aria("note one")
    store.tell_aria("note two")
    store.send_to_human("unrelated ask")
    assert {r.request_id for r in store.list_for_aria()} == {
        r.request_id for r in store.list_open(direction=DIRECTION_TO_ARIA)
    }
    assert len(store.list_for_aria()) == 2


def test_open_count_respects_direction(store):
    store.send_to_human("ask 1")
    store.send_to_human("ask 2")
    store.tell_aria("note 1")
    assert store.open_count(direction=DIRECTION_TO_HUMAN) == 2
    assert store.open_count(direction=DIRECTION_TO_ARIA) == 1
    assert store.open_count() == 3


def test_list_open_with_no_direction_filter_returns_both():
    from sovereign_agent.persistence.store import ErebloStore as ES
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        s = RequestStore(ES(Path(d) / "atoms.db"))
        s.send_to_human("ask")
        s.tell_aria("note")
        assert len(s.list_open()) == 2


# ─── SendToHumanTool / ReadInboxTool ────────────────────────────────────────


def test_send_to_human_tool_and_read_inbox_tool_round_trip():
    from sovereign_agent.tools.inbox_tools import ReadInboxTool, SendToHumanTool

    send = SendToHumanTool()
    result = asyncio.run(send.execute(
        SendToHumanTool.Args(title="a question for Kevin", kind="question"),
        trace_id="t1",
    ))
    assert result.ok
    assert result.output["direction"] == DIRECTION_TO_HUMAN
    assert result.output["live_chat"] is True

    # SendToHumanTool's message must not appear in Aria's own inbox.
    read = ReadInboxTool()
    read_result = asyncio.run(read.execute(ReadInboxTool.Args(), trace_id="t2"))
    assert read_result.ok
    assert read_result.output["count"] == 0

    # Now leave a note the other direction and confirm ReadInboxTool sees it.
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore as ES
    from sovereign_agent.workflow.requests import RequestStore as RS
    rs = RS(ES(SETTINGS.paths.atoms_db))
    rs.tell_aria("a note for Aria")

    read_result_2 = asyncio.run(read.execute(ReadInboxTool.Args(), trace_id="t3"))
    assert read_result_2.ok
    assert read_result_2.output["count"] == 1
    assert read_result_2.output["notes"][0]["title"] == "a note for Aria"


# ─── AcknowledgeInboxTool (inbox-empty-d) ───────────────────────────────────
# Kevin, 2026-07-26: "she needs to be emptying her inbox... keep her inbox
# empty." read_inbox only ever READ notes — nothing closed the loop.


def test_acknowledge_inbox_note_closes_it_and_it_leaves_the_open_list():
    from sovereign_agent.tools.inbox_tools import AcknowledgeInboxTool, ReadInboxTool
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore as ES
    from sovereign_agent.workflow.requests import RequestStore as RS

    rs = RS(ES(SETTINGS.paths.atoms_db))
    req = rs.tell_aria("please read this before you build anything else")

    read = ReadInboxTool()
    before = asyncio.run(read.execute(ReadInboxTool.Args(), trace_id="t1"))
    assert before.output["count"] == 1

    ack = AcknowledgeInboxTool()
    result = asyncio.run(ack.execute(
        AcknowledgeInboxTool.Args(request_id=req.request_id), trace_id="t2"))
    assert result.ok
    assert result.output["status"] == "resolved"

    after = asyncio.run(read.execute(ReadInboxTool.Args(), trace_id="t3"))
    assert after.output["count"] == 0


def test_acknowledge_inbox_note_accepts_a_short_id():
    from sovereign_agent.tools.inbox_tools import AcknowledgeInboxTool
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.persistence.store import ErebloStore as ES
    from sovereign_agent.workflow.requests import RequestStore as RS

    rs = RS(ES(SETTINGS.paths.atoms_db))
    req = rs.tell_aria("a note")

    ack = AcknowledgeInboxTool()
    result = asyncio.run(ack.execute(
        AcknowledgeInboxTool.Args(request_id=req.short_id), trace_id="t1"))
    assert result.ok
    assert result.output["request_id"] == req.request_id


def test_acknowledge_inbox_note_unknown_id_reports_not_found():
    from sovereign_agent.tools.inbox_tools import AcknowledgeInboxTool

    ack = AcknowledgeInboxTool()
    result = asyncio.run(ack.execute(
        AcknowledgeInboxTool.Args(request_id="not-a-real-id-at-all"), trace_id="t1"))
    assert not result.ok
    assert "not_found" in result.error
