"""
test_command_master.py — Tests for M31 (run_command, edit_in_place).
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "run_command" in _TIER_REGISTRY
    assert "edit_in_place" in _TIER_REGISTRY
    assert _TIER_REGISTRY["run_command"].tier == 1
    assert _TIER_REGISTRY["edit_in_place"].tier == 1


def test_command_allowlist_has_expanded_tools():
    from sovereign_agent.tools.command_master import COMMAND_ALLOWLIST
    for expected in ["make", "git", "rg", "jq", "awk", "sed", "curl", "uv"]:
        assert expected in COMMAND_ALLOWLIST, f"{expected!r} missing from COMMAND_ALLOWLIST"


@pytest.mark.asyncio
async def test_run_command_allowed(tmp_path):
    """run_command executes an allowed command and returns output."""
    from sovereign_agent.tools.command_master import RunCommandTool

    tool = RunCommandTool()
    result = await tool.execute(
        tool.Args(argv=["echo", "hello-world"], cwd=str(tmp_path)),
        trace_id="t1",
    )
    assert result.ok
    assert result.output["exit_code"] == 0
    assert result.output["succeeded"] is True
    assert "hello-world" in result.output["stdout"]


@pytest.mark.asyncio
async def test_run_command_rejected_not_in_allowlist():
    """run_command rejects commands not in the allowlist."""
    from sovereign_agent.tools.command_master import RunCommandTool

    tool = RunCommandTool()
    result = await tool.execute(
        tool.Args(argv=["rm", "-rf", "/"]),
        trace_id="t1",
    )
    assert not result.ok
    assert "allowlist" in result.error


@pytest.mark.asyncio
async def test_run_command_rejects_metacharacter():
    """run_command rejects arguments containing shell metacharacters."""
    from sovereign_agent.tools.command_master import RunCommandTool

    tool = RunCommandTool()
    result = await tool.execute(
        tool.Args(argv=["echo", "hello; rm -rf /"]),
        trace_id="t1",
    )
    assert not result.ok
    assert "metacharacter" in result.error


@pytest.mark.asyncio
async def test_run_command_timeout():
    """run_command returns error on timeout.

    The script argument uses a real newline, not a semicolon, to separate
    statements — a semicolon trips run_command's own metacharacter guard
    before the timeout logic ever runs (confirmed: an earlier version of
    this test used "import time; time.sleep(10)" and got "shell
    metacharacter in argument" instead of the intended "timed out" error).
    """
    from sovereign_agent.tools.command_master import RunCommandTool

    tool = RunCommandTool()
    result = await tool.execute(
        tool.Args(argv=["python3", "-c", "import time\ntime.sleep(10)"], timeout=1),
        trace_id="t1",
    )
    assert not result.ok
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_edit_in_place_success(tmp_path):
    """edit_in_place replaces text in a file within an allowed root."""
    from sovereign_agent.tools.command_master import EditInPlaceTool

    target = tmp_path / "test.py"
    target.write_text("def old_func():\n    pass\n")

    tool = EditInPlaceTool()
    with patch("sovereign_agent.tools.command_master._allowed_roots", return_value=[tmp_path]):
        result = await tool.execute(
            tool.Args(
                path=str(target),
                old_text="def old_func():\n    pass\n",
                new_text="def new_func():\n    return 42\n",
            ),
            trace_id="t1",
        )

    assert result.ok
    assert "diff" in result.output
    assert target.read_text() == "def new_func():\n    return 42\n"


@pytest.mark.asyncio
async def test_edit_in_place_not_found(tmp_path):
    """edit_in_place returns error when old_text is not in file."""
    from sovereign_agent.tools.command_master import EditInPlaceTool

    target = tmp_path / "test.py"
    target.write_text("def foo():\n    pass\n")

    tool = EditInPlaceTool()
    with patch("sovereign_agent.tools.command_master._allowed_roots", return_value=[tmp_path]):
        result = await tool.execute(
            tool.Args(path=str(target), old_text="def bar():", new_text="def baz():"),
            trace_id="t1",
        )

    assert not result.ok
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_edit_in_place_scope_violation(tmp_path):
    """edit_in_place rejects paths outside allowed roots."""
    from sovereign_agent.tools.command_master import EditInPlaceTool

    tool = EditInPlaceTool()
    allowed = tmp_path / "sandbox"
    allowed.mkdir()

    with patch("sovereign_agent.tools.command_master._allowed_roots", return_value=[allowed]):
        result = await tool.execute(
            tool.Args(
                path=str(tmp_path / "outside.py"),
                old_text="x",
                new_text="y",
            ),
            trace_id="t1",
        )

    assert not result.ok
    assert "outside allowed roots" in result.error


def test_loop_has_terminal_discipline():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "terminal-discipline-d" in src, \
                "TERMINAL DISCIPLINE section missing — run apply_command_master.sh"
            return
        p = p.parent
    pytest.skip("loop.py not found")


def test_runner_allowlist_expanded():
    from sovereign_agent.tools.runner import SHELL_ALLOWLIST
    assert "git" in SHELL_ALLOWLIST
    assert "rg" in SHELL_ALLOWLIST
    assert "jq" in SHELL_ALLOWLIST
