"""Behavior tests for aria-atelier (Workstream A) — prove the patched
cockpit + loop actually work, using a shadow copy of the whole package
(never touches real src/). STAGED ONLY: this file is never promoted to
live tests/ — see test_atelier_live.py, which is what gets copied to the
promoted/live `tests/` dir instead (plain imports, zero sys.modules
manipulation, learned the hard way twice already this session)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-atelier" / "patcher.py").is_file():
            return candidate / "aria-atelier"
    raise RuntimeError("could not locate aria-atelier/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_app, patch_loop

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "sovereign_agent")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    app_py = shadow / "sovereign_agent" / "cockpit" / "app.py"
    patched_app, _ = patch_app(app_py.read_text(encoding="utf-8"))
    app_py.write_text(patched_app, encoding="utf-8")

    loop_py = shadow / "sovereign_agent" / "loop.py"
    patched_loop, _ = patch_loop(loop_py.read_text(encoding="utf-8"))
    loop_py.write_text(patched_loop, encoding="utf-8")

    work_events_src = (
        STAGING / "payload" / "src" / "sovereign_agent" / "work_events.py"
    )
    (shadow / "sovereign_agent" / "work_events.py").write_text(
        work_events_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return shadow


@pytest.fixture
def shadow_pkg(tmp_path, monkeypatch):
    """Import sovereign_agent from the shadow copy, saving and restoring
    sys.modules so this never pollutes later tests in the same process.
    Legitimate here (staged, pre-apply verification only — never promoted)."""
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent
        yield sovereign_agent
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


# ── work_events.py unit tests ───────────────────────────────────────────


def test_write_file_emits_work_write_event(shadow_pkg, monkeypatch):
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


def test_edit_file_emits_work_edit_event_with_diff_counts(shadow_pkg, monkeypatch):
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


def test_run_command_emits_work_command_event_with_cmd_string(shadow_pkg, monkeypatch):
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


def test_failed_tool_call_never_emits_a_work_event(shadow_pkg, monkeypatch):
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


def test_unrecognized_tool_never_emits_a_work_event(shadow_pkg, monkeypatch):
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


def test_maybe_emit_work_event_never_raises_on_garbage_input(shadow_pkg):
    from sovereign_agent.work_events import maybe_emit_work_event

    # None result, None args, garbage tool name — must be a silent no-op.
    maybe_emit_work_event("write_file", None, None, trace_id="t1")
    maybe_emit_work_event("garbage", object(), object(), trace_id="t1")


# ── cockpit pane / rendering tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_atelier_pane_exists_and_is_empty_on_boot(shadow_pkg):
    from sovereign_agent.cockpit import CockpitApp
    from textual.widgets import RichLog

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        atelier = app.query_one("#atelier-log", RichLog)
        assert atelier is not None
        assert len(atelier.lines) == 0


@pytest.mark.asyncio
async def test_render_event_routes_work_write_to_atelier_pane_not_live_pane(shadow_pkg):
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
        assert len(events_log.lines) == lines_before_events  # untouched


@pytest.mark.asyncio
async def test_render_event_still_routes_generic_flags_to_live_pane_as_before(shadow_pkg):
    """Regression guard: adding the work- routing branch must not disturb
    any existing flag's behavior."""
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
        assert len(atelier.lines) == lines_before_atelier  # untouched


@pytest.mark.asyncio
async def test_render_work_event_colorizes_edit_with_diff_lines(shadow_pkg):
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
async def test_render_work_event_shows_command_string(shadow_pkg):
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
