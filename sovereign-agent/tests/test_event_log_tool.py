"""Tests for sub-events-tool-d — log_events/read_events: Aria's own tool
surface over the events.py sub-event mechanism (emit_child_event /
event_children).

Kevin, 2026-07-21: "make the sub event system where she can intelligently
call on other events she can send a queue of events to be used."
"""
from __future__ import annotations

import pytest


def test_tools_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "log_events" in _TIER_REGISTRY
    assert "read_events" in _TIER_REGISTRY
    assert _TIER_REGISTRY["log_events"].tier == 1
    assert _TIER_REGISTRY["read_events"].tier == 1


@pytest.mark.asyncio
async def test_log_events_emits_a_queue_as_top_level_events():
    from sovereign_agent.events import force_fsync, init_events_db, tail_to_sqlite
    from sovereign_agent.tools.event_log_tool import LogEventsTool

    tool = LogEventsTool()
    result = await tool.execute(
        tool.Args(
            trace_id="t1",
            events=[
                {"flag": "plan-step-d", "note": "step one"},
                {"flag": "plan-step-d", "note": "step two"},
            ],
        ),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["count"] == 2
    ids = result.output["event_ids"]
    assert len(ids) == 2 and len(set(ids)) == 2  # distinct real ids

    force_fsync()
    conn = init_events_db()
    tail_to_sqlite(conn)
    rows = conn.execute(
        "SELECT event_id, parent_id FROM events WHERE event_id IN (?, ?)",
        tuple(ids),
    ).fetchall()
    assert len(rows) == 2
    assert all(r[1] is None for r in rows)  # no parent given -> top-level


@pytest.mark.asyncio
async def test_log_events_with_a_parent_id_makes_them_all_children():
    from sovereign_agent.events import emit_event, force_fsync, init_events_db, tail_to_sqlite
    from sovereign_agent.tools.event_log_tool import LogEventsTool

    parent_id = emit_event("subtask-start-d", plane="control", trace_id="t1")
    tool = LogEventsTool()
    result = await tool.execute(
        tool.Args(
            trace_id="t1",
            parent_id=parent_id,
            events=[
                {"flag": "sub-step-d", "note": "a"},
                {"flag": "sub-step-d", "note": "b"},
                {"flag": "sub-step-d", "note": "c"},
            ],
        ),
        trace_id="t1",
    )
    assert result.ok
    force_fsync()
    conn = init_events_db()
    tail_to_sqlite(conn)

    from sovereign_agent.events import event_children
    children = event_children(parent_id, conn=conn)
    assert {c["event_id"] for c in children} == set(result.output["event_ids"])


@pytest.mark.asyncio
async def test_log_events_chain_mode_links_each_to_the_previous():
    from sovereign_agent.events import force_fsync, init_events_db, tail_to_sqlite
    from sovereign_agent.tools.event_log_tool import LogEventsTool

    tool = LogEventsTool()
    result = await tool.execute(
        tool.Args(
            trace_id="t1", chain=True,
            events=[
                {"flag": "step-1-d"},
                {"flag": "step-2-d"},
                {"flag": "step-3-d"},
            ],
        ),
        trace_id="t1",
    )
    assert result.ok
    ids = result.output["event_ids"]
    force_fsync()
    conn = init_events_db()
    tail_to_sqlite(conn)
    rows = {r[0]: r[1] for r in conn.execute(
        "SELECT event_id, parent_id FROM events WHERE event_id IN (?, ?, ?)",
        tuple(ids),
    ).fetchall()}
    assert rows[ids[0]] is None       # first has no parent
    assert rows[ids[1]] == ids[0]     # second's parent is the first
    assert rows[ids[2]] == ids[1]     # third's parent is the second


@pytest.mark.asyncio
async def test_log_events_rejects_more_than_the_bounded_max():
    from sovereign_agent.tools.event_log_tool import LogEventsTool, _MAX_QUEUE

    try:
        LogEventsTool.Args(
            trace_id="t1",
            events=[{"flag": f"f-{i}-d"} for i in range(_MAX_QUEUE + 1)],
        )
        assert False, "expected a validation error over the bounded max"
    except Exception:
        pass


@pytest.mark.asyncio
async def test_read_events_returns_the_children_just_logged():
    from sovereign_agent.tools.event_log_tool import LogEventsTool, ReadEventsTool

    log_tool = LogEventsTool()
    logged = await log_tool.execute(
        log_tool.Args(
            trace_id="t1",
            events=[{"flag": "note-d", "note": "hello"},
                    {"flag": "note-d", "note": "world"}],
        ),
        trace_id="t1",
    )
    parent_id = logged.output["event_ids"][0]
    # nest the second one under the first, then read it back
    log_tool2_result = await log_tool.execute(
        log_tool.Args(trace_id="t1", parent_id=parent_id,
                     events=[{"flag": "child-d", "note": "nested"}]),
        trace_id="t1",
    )

    read_tool = ReadEventsTool()
    result = await read_tool.execute(
        read_tool.Args(parent_id=parent_id), trace_id="t1",
    )
    assert result.ok
    assert result.output["count"] == 1
    child = result.output["children"][0]
    assert child["flag"] == "child-d"
    assert child["payload"]["note"] == "nested"
    assert child["event_id"] == log_tool2_result.output["event_ids"][0]


@pytest.mark.asyncio
async def test_read_events_empty_is_ok_not_an_error():
    from sovereign_agent.tools.event_log_tool import ReadEventsTool

    tool = ReadEventsTool()
    result = await tool.execute(
        tool.Args(parent_id="nothing-was-ever-logged-here"), trace_id="t1",
    )
    assert result.ok
    assert result.output["count"] == 0
    assert result.output["children"] == []
