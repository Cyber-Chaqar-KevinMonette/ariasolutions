"""Behavior tests for aria-atelier, promoted to live tests/ — tests the
REAL, already-patched `sovereign_agent.loop` / `sovereign_agent.cockpit.app`
/ `sovereign_agent.work_events` directly, no shadow copy, no `sys.modules`
manipulation.

The staged `test_atelier.py` (stays in `aria-atelier/tests/`, never
promoted) uses a shadow-copy-and-patch mechanism to verify the patch
functions work correctly BEFORE the code is applied to live. Once applied,
that mechanism is unnecessary — and this session found twice
(`test_locator_events_fix.py`, `test_security_strip_wire.py`) that
promoting a shadow-copy test file to live tests/ can actively pollute
unrelated tests elsewhere in the suite. Root-cause fix: don't do it. Test
the real, live module directly, exactly like test_cockpit.py does.
"""
from __future__ import annotations

import json

import pytest


# ── work_events.py unit tests ───────────────────────────────────────────


def test_write_file_emits_work_write_event(monkeypatch):
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.write_file import _Args as WriteArgs
    from sovereign_agent.work_events import maybe_emit_work_event

    captured = {}

    def fake_emit(flag, *, plane, trace_id, payload=None, parent_id=None):
        captured["flag"] = flag
        captured["plane"] = plane
        captured["payload"] = payload
        return "fake-id"

    monkeypatch.setattr("sovereign_agent.work_events.emit_event", fake_emit)

    args = WriteArgs(path="/tmp/foo.py", content="line1\nline2\n")
    result = ToolResult(ok=True, output={"path": "/tmp/foo.py", "bytes_written": 12})
    maybe_emit_work_event("write_file", args, result, trace_id="t1")

    assert captured["flag"] == "work-write"
    assert captured["plane"] == "work"
    assert captured["payload"]["op"] == "write"
    assert captured["payload"]["path"] == "/tmp/foo.py"
    assert captured["payload"]["added"] == 2


def test_edit_file_emits_work_edit_event_with_diff_counts(monkeypatch):
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.edit_file import _Args as EditArgs
    from sovereign_agent.work_events import maybe_emit_work_event

    captured = {}

    def fake_emit(flag, *, plane, trace_id, payload=None, parent_id=None):
        captured["flag"] = flag
        captured["payload"] = payload
        return "fake-id"

    monkeypatch.setattr("sovereign_agent.work_events.emit_event", fake_emit)

    args = EditArgs(path="/tmp/foo.py", old_str="a\nb\n", new_str="a\nb\nc\n")
    result = ToolResult(ok=True, output={"path": "/tmp/foo.py"})
    maybe_emit_work_event("edit_file", args, result, trace_id="t1")

    assert captured["flag"] == "work-edit"
    assert captured["payload"]["op"] == "edit"
    assert captured["payload"]["added"] >= 1


def test_run_command_emits_work_command_event_with_cmd_string(monkeypatch):
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.command_master import RunCommandTool
    from sovereign_agent.work_events import maybe_emit_work_event

    captured = {}

    def fake_emit(flag, *, plane, trace_id, payload=None, parent_id=None):
        captured["flag"] = flag
        captured["payload"] = payload
        return "fake-id"

    monkeypatch.setattr("sovereign_agent.work_events.emit_event", fake_emit)

    args = RunCommandTool.Args(argv=["git", "status"])
    result = ToolResult(ok=True, output={"exit_code": 0, "command": "git status"})
    maybe_emit_work_event("run_command", args, result, trace_id="t1")

    assert captured["flag"] == "work-command"
    assert captured["payload"]["cmd"] == "git status"


def test_failed_tool_call_never_emits_a_work_event(monkeypatch):
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.tools.write_file import _Args as WriteArgs
    from sovereign_agent.work_events import maybe_emit_work_event

    called = []
    monkeypatch.setattr(
        "sovereign_agent.work_events.emit_event",
        lambda *a, **k: called.append(1),
    )

    args = WriteArgs(path="/tmp/foo.py", content="x")
    result = ToolResult(ok=False, error="disk full")
    maybe_emit_work_event("write_file", args, result, trace_id="t1")

    assert called == []


def test_unrecognized_tool_never_emits_a_work_event(monkeypatch):
    from sovereign_agent.tools.base import ToolResult
    from sovereign_agent.work_events import maybe_emit_work_event

    called = []
    monkeypatch.setattr(
        "sovereign_agent.work_events.emit_event",
        lambda *a, **k: called.append(1),
    )

    class _FakeArgs:
        pass

    result = ToolResult(ok=True, output={})
    maybe_emit_work_event("some_read_only_tool", _FakeArgs(), result, trace_id="t1")

    assert called == []


def test_maybe_emit_work_event_never_raises_on_garbage_input():
    from sovereign_agent.work_events import maybe_emit_work_event

    maybe_emit_work_event("write_file", None, None, trace_id="t1")
    maybe_emit_work_event("garbage", object(), object(), trace_id="t1")


# ── cockpit pane / rendering tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_atelier_pane_exists_and_is_empty_on_boot():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)
        assert atelier is not None
        assert len(atelier.lines) == 0


@pytest.mark.asyncio
async def test_render_event_routes_work_write_to_atelier_pane_not_live_pane():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)
        events_log = app.query_one("#events-log", RichLog)
        lines_before_events = len(events_log.lines)

        raw = json.dumps({
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-write",
            "payload": {"op": "write", "path": "/tmp/new.py", "added": 3, "diff_excerpt": "hi"},
        })
        app._render_event(raw)
        await pilot.pause()

        assert len(atelier.lines) > 0
        assert any("new.py" in str(line) for line in atelier.lines)
        assert len(events_log.lines) == lines_before_events


@pytest.mark.asyncio
async def test_render_event_still_routes_generic_flags_to_live_pane_as_before():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)
        events_log = app.query_one("#events-log", RichLog)
        lines_before_atelier = len(atelier.lines)

        raw = json.dumps({
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "trace-start-d",
            "payload": {},
        })
        app._render_event(raw)
        await pilot.pause()

        assert len(events_log.lines) > 0
        assert len(atelier.lines) == lines_before_atelier


@pytest.mark.asyncio
async def test_render_work_event_colorizes_edit_with_diff_lines():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)

        ev = {
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-edit",
            "payload": {
                "op": "edit",
                "path": "/tmp/mod.py",
                "added": 2,
                "removed": 1,
                "diff_excerpt": "+new line\n-old line\n context",
            },
        }
        app._render_work_event(ev)
        await pilot.pause()

        rendered = "\n".join(str(line) for line in atelier.lines)
        assert "mod.py" in rendered
        assert "new line" in rendered
        assert "old line" in rendered


@pytest.mark.asyncio
async def test_render_work_event_shows_command_string():
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)

        ev = {
            "ts": "2026-07-03T14:00:00.000Z",
            "flag": "work-command",
            "payload": {"op": "command", "cmd": "pytest tests/test_foo.py"},
        }
        app._render_work_event(ev)
        await pilot.pause()

        rendered = "\n".join(str(line) for line in atelier.lines)
        assert "pytest tests/test_foo.py" in rendered
