"""
test_cron_internal.py — Tests for cron scheduling (M24).
"""
from __future__ import annotations
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


# ── cron matching ─────────────────────────────────────────────────────────

def test_wildcard_matches_any():
    from sovereign_agent.schedule import _field_matches
    assert _field_matches("*", 0)
    assert _field_matches("*", 59)
    assert _field_matches("*", 23)


def test_exact_value_matches():
    from sovereign_agent.schedule import _field_matches
    assert _field_matches("8", 8)
    assert not _field_matches("8", 9)


def test_step_matches():
    from sovereign_agent.schedule import _field_matches
    assert _field_matches("*/15", 0)
    assert _field_matches("*/15", 15)
    assert _field_matches("*/15", 30)
    assert _field_matches("*/15", 45)
    assert not _field_matches("*/15", 7)


def test_cron_daily_at_8am():
    from sovereign_agent.schedule import cron_matches
    dt = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)   # Friday 08:00 UTC
    assert cron_matches("0 8 * * *", dt)
    dt2 = datetime(2026, 6, 19, 8, 1, tzinfo=timezone.utc)
    assert not cron_matches("0 8 * * *", dt2)


def test_cron_weekly_monday():
    from sovereign_agent.schedule import cron_matches
    # Monday 2026-06-22
    dt_mon = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
    assert cron_matches("0 9 * * 1", dt_mon)
    # Tuesday 2026-06-23
    dt_tue = datetime(2026, 6, 23, 9, 0, tzinfo=timezone.utc)
    assert not cron_matches("0 9 * * 1", dt_tue)


def test_cron_every_30_minutes():
    from sovereign_agent.schedule import cron_matches
    dt = datetime(2026, 6, 19, 14, 30, tzinfo=timezone.utc)
    assert cron_matches("*/30 * * * *", dt)
    dt2 = datetime(2026, 6, 19, 14, 0, tzinfo=timezone.utc)
    assert cron_matches("*/30 * * * *", dt2)
    dt3 = datetime(2026, 6, 19, 14, 15, tzinfo=timezone.utc)
    assert not cron_matches("*/30 * * * *", dt3)


def test_cron_invalid_fields():
    from sovereign_agent.schedule import cron_matches
    dt = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)
    assert not cron_matches("too few", dt)
    assert not cron_matches("0 8 * *", dt)


# ── ScheduleStore ─────────────────────────────────────────────────────────

def test_schedule_store_empty(tmp_path):
    from sovereign_agent.schedule import ScheduleStore
    store = ScheduleStore(tmp_path / "schedule.yaml")
    assert store.load() == []


def test_schedule_store_add_and_load(tmp_path):
    from sovereign_agent.schedule import ScheduleEntry, ScheduleStore
    store = ScheduleStore(tmp_path / "schedule.yaml")
    entry = ScheduleEntry(
        name="daily-sentinel",
        cron="0 8 * * *",
        directive="check sentinel health",
    )
    store.add(entry)
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].name == "daily-sentinel"
    assert loaded[0].cron == "0 8 * * *"


def test_schedule_store_add_replaces_same_name(tmp_path):
    from sovereign_agent.schedule import ScheduleEntry, ScheduleStore
    store = ScheduleStore(tmp_path / "schedule.yaml")
    e1 = ScheduleEntry(name="s1", cron="0 8 * * *", directive="old")
    e2 = ScheduleEntry(name="s1", cron="0 9 * * *", directive="new")
    store.add(e1)
    store.add(e2)
    entries = store.load()
    assert len(entries) == 1
    assert entries[0].directive == "new"


def test_schedule_store_remove(tmp_path):
    from sovereign_agent.schedule import ScheduleEntry, ScheduleStore
    store = ScheduleStore(tmp_path / "schedule.yaml")
    store.add(ScheduleEntry(name="s1", cron="0 8 * * *", directive="task1"))
    store.add(ScheduleEntry(name="s2", cron="0 9 * * *", directive="task2"))
    removed = store.remove("s1")
    assert removed
    entries = store.load()
    assert len(entries) == 1
    assert entries[0].name == "s2"


# ── check_and_inject_due ──────────────────────────────────────────────────

def test_check_and_inject_due_injects_due_entry(tmp_path):
    from sovereign_agent.schedule import ScheduleEntry, ScheduleStore, check_and_inject_due

    store = ScheduleStore(tmp_path / "schedule.yaml")
    store.add(ScheduleEntry(
        name="test-daily",
        cron="0 8 * * *",
        directive="run daily check",
    ))

    injected_tasks = []

    def fake_add_task(*, goal, priority, mode, task_id):
        injected_tasks.append(goal)

    now = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)
    with patch("sovereign_agent.mode_controller.add_task", fake_add_task):
        result = check_and_inject_due(store, now=now)

    assert "test-daily" in result
    assert "run daily check" in injected_tasks


def test_check_and_inject_due_skips_non_due(tmp_path):
    from sovereign_agent.schedule import ScheduleEntry, ScheduleStore, check_and_inject_due

    store = ScheduleStore(tmp_path / "schedule.yaml")
    store.add(ScheduleEntry(
        name="only-at-8",
        cron="0 8 * * *",
        directive="morning check",
    ))

    injected_tasks = []

    def fake_add_task(*, goal, priority, mode, task_id):
        injected_tasks.append(goal)

    now = datetime(2026, 6, 19, 9, 30, tzinfo=timezone.utc)  # 09:30, not 08:00
    with patch("sovereign_agent.mode_controller.add_task", fake_add_task):
        result = check_and_inject_due(store, now=now)

    assert result == []
    assert injected_tasks == []


def test_check_and_inject_due_deduplicates_within_minute(tmp_path):
    """Same schedule should not be injected twice in the same minute."""
    from sovereign_agent.schedule import ScheduleEntry, ScheduleStore, check_and_inject_due

    store = ScheduleStore(tmp_path / "schedule.yaml")
    store.add(ScheduleEntry(
        name="once-per-minute",
        cron="* * * * *",
        directive="frequent task",
    ))

    count = [0]

    def fake_add_task(*, goal, priority, mode, task_id):
        count[0] += 1

    now = datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)
    with patch("sovereign_agent.mode_controller.add_task", fake_add_task):
        check_and_inject_due(store, now=now)
        check_and_inject_due(store, now=now)

    assert count[0] == 1


# ── schedule_task tool ────────────────────────────────────────────────────

def test_tool_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "schedule_task" in _TIER_REGISTRY
    assert _TIER_REGISTRY["schedule_task"].tier == 1


@pytest.mark.asyncio
async def test_schedule_tool_adds_entry(tmp_path):
    from sovereign_agent.tools.schedule_tool import ScheduleTaskTool

    with patch("sovereign_agent.tools.schedule_tool._schedule_path", return_value=tmp_path / "schedule.yaml"):
        # Also patch schedule.py's _schedule_path to same location
        tool = ScheduleTaskTool()
        result = await tool.execute(
            tool.Args(
                name="weekly-memory-tending",
                directive="tend memory and summarize recent atoms",
                cron="0 9 * * 1",
                description="Every Monday morning",
            ),
            trace_id="t1",
        )

    assert result.ok, result.error
    assert "weekly-memory-tending" in result.output

    from sovereign_agent.schedule import ScheduleStore
    entries = ScheduleStore(tmp_path / "schedule.yaml").load()
    assert len(entries) == 1
    assert entries[0].name == "weekly-memory-tending"


@pytest.mark.asyncio
async def test_schedule_tool_rejects_bad_cron(tmp_path):
    from sovereign_agent.tools.schedule_tool import ScheduleTaskTool

    with patch("sovereign_agent.tools.schedule_tool._schedule_path", return_value=tmp_path / "schedule.yaml"):
        tool = ScheduleTaskTool()
        result = await tool.execute(
            tool.Args(name="bad", directive="something", cron="0 8 * *"),
            trace_id="t1",
        )

    assert not result.ok
    assert "5 fields" in result.error
