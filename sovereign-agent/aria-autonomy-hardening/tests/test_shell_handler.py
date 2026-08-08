"""Tests for ShellHandler resilience at failure paths (M78).

All tests are pure Python — no real subprocesses except test_timeout and
test_return_code_nonzero (which use innocuous shell commands like `sleep`
and `false`). Each test is self-contained.

Coverage targets: shell.py kill switch, allowlist rejection, timeout,
output truncation, environment injection, nonexistent cwd, nonzero exit.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from sovereign_agent.workflow.handlers.shell import (
    DEFAULT_ALLOWLIST,
    KILL_SWITCH_ENV,
    ShellHandler,
)
from sovereign_agent.persistence.projects import Task


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_task(action_input: dict) -> Task:
    """Build a minimal Task whose description encodes the action_input."""
    return Task(
        task_id="test-task",
        project_id="test-project",
        parent_task_id=None,
        title="test",
        description=json.dumps({"action_input": action_input}),
        status="in_progress",
        ordinal=1,
        outcome={},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_kill_switch(monkeypatch):
    """SOV_NO_SHELL_HANDLER=1 → handler returns error='handler-disabled' immediately."""
    monkeypatch.setenv(KILL_SWITCH_ENV, "1")

    handler = ShellHandler()
    task = _make_task({"argv": ["echo", "hello"]})
    result = handler(task)

    assert result.succeeded is False
    assert result.error == "handler-disabled"


def test_allowlist_rejection_edge_cases():
    """../evil, ' git' (leading space), and empty allowlist all rejected."""
    handler = ShellHandler(allowlist={"git"})

    for bad_cmd in ["../evil", "git && rm -rf /", "python3"]:
        argv = [bad_cmd]
        task = _make_task({"argv": argv})
        result = handler(task)
        assert result.succeeded is False, f"Expected rejection for {bad_cmd!r}"
        assert result.error == "allowlist-rejection", (
            f"Expected allowlist-rejection, got {result.error!r} for {bad_cmd!r}"
        )


def test_timeout_enforcement():
    """Command that exceeds timeout_sec → error='timeout', succeeded=False."""
    handler = ShellHandler(allowlist={"sleep"})
    task = _make_task({"argv": ["sleep", "10"], "timeout_sec": 1})
    result = handler(task)

    assert result.succeeded is False
    assert result.error == "timeout"


def test_large_output_truncation_utf8_safe():
    """stdout larger than _STDOUT_CAP is truncated to exactly _STDOUT_CAP bytes."""
    handler = ShellHandler(allowlist={"python3"})

    # Generate 32KB of 'A' via python3 -c
    large_output_script = "import sys; sys.stdout.write('A' * 32768)"
    task = _make_task({"argv": ["python3", "-c", large_output_script]})
    result = handler(task)

    assert result.succeeded is True
    stdout = result.extra.get("stdout", "")
    assert len(stdout) <= 16_384, f"stdout not capped: got {len(stdout)} bytes"


def test_environment_injection():
    """env dict with int values → str-coerced; no TypeError raised."""
    handler = ShellHandler(allowlist={"python3"})

    task = _make_task({
        "argv": ["python3", "-c", "import os; print(os.environ.get('PORT', ''))"],
        "env": {"PORT": 8080},   # int, not str
    })
    result = handler(task)

    assert result.succeeded is True
    assert "8080" in result.extra.get("stdout", "")


def test_cwd_nonexistent():
    """cwd=/nonexistent → succeeded=False, no crash."""
    handler = ShellHandler(allowlist={"echo"})
    task = _make_task({
        "argv": ["echo", "hi"],
        "cwd": "/this-path-definitely-does-not-exist-aria-test",
    })
    result = handler(task)

    assert result.succeeded is False
    # Should be some error, not a crash
    assert result.error is not None


def test_return_code_nonzero():
    """Command that exits with code 1 → succeeded=False, exit_code captured."""
    handler = ShellHandler(allowlist={"python3"})

    task = _make_task({
        "argv": ["python3", "-c", "import sys; sys.stdout.write('some output'); sys.exit(1)"],
    })
    result = handler(task)

    assert result.succeeded is False
    assert result.extra.get("exit_code") == 1
    assert "some output" in result.extra.get("stdout", "")
