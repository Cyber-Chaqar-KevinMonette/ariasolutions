"""
test_observatory.py — structural tests for M29 (observatory).

These tests verify the patch markers are present in the source files,
confirming apply_observatory.sh ran successfully. The actual emission
behaviour is exercised by the loop's existing test coverage.
"""
from __future__ import annotations
import pathlib


def _src(name: str) -> str:
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / name
        if c.exists():
            return c.read_text()
        p = p.parent
    raise FileNotFoundError(f"{name} not found")


def _app() -> str:
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "cockpit" / "app.py"
        if c.exists():
            return c.read_text()
        p = p.parent
    raise FileNotFoundError("cockpit/app.py not found")


def test_loop_emits_token_usage():
    src = _src("loop.py")
    assert "observatory-token-d" in src, \
        "token-usage-d emission missing — run apply_observatory.sh"
    assert '"token-usage-d"' in src


def test_loop_emits_tool_start():
    src = _src("loop.py")
    assert "observatory-tool-start-d" in src, \
        "tool-start-d emission missing — run apply_observatory.sh"
    assert '"tool-start-d"' in src
    assert "args_summary" in src


def test_loop_tool_start_before_execute():
    """tool-start-d must be recorded BEFORE tool.execute() is called."""
    src = _src("loop.py")
    start_pos = src.find("tool-start-d")
    exec_pos = src.find("await tool.execute(parsed, trace_id=trace_id)")
    assert start_pos != -1 and exec_pos != -1
    assert start_pos < exec_pos, \
        "tool-start-d must appear before tool.execute() in loop.py"


def test_app_has_observatory_vars():
    src = _app()
    assert "observatory-status-d" in src, \
        "_last_tool/_session_tokens missing — run apply_observatory.sh"
    assert "_last_tool" in src
    assert "_session_tokens" in src


def test_app_render_event_handles_tool_start():
    src = _app()
    assert "observatory-render-d" in src
    assert '"tool-start-d"' in src or "== \"tool-start-d\"" in src


def test_app_render_event_handles_token_usage():
    src = _app()
    assert '"token-usage-d"' in src or "== \"token-usage-d\"" in src
    assert "running_total" in src


def test_app_activity_slash_command():
    src = _app()
    assert "observatory-activity-d" in src, \
        "/activity handler missing — run apply_observatory.sh"
    assert "_show_activity_log" in src


def test_app_show_activity_log_method():
    src = _app()
    assert "def _show_activity_log" in src
    assert "tool-start-d" in src
    assert "token-usage-d" in src
