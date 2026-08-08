"""
test_git_tools.py — Tests for Tier 0 git read tools.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
import pytest


def test_tools_registered():
    """All five git tools must be registered in the tier registry."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    for name in ("git_log", "git_diff", "git_status", "git_show", "git_blame"):
        assert name in _TIER_REGISTRY, f"{name} not registered"
        assert _TIER_REGISTRY[name].tier == 0, f"{name} must be Tier 0"


def test_all_tools_have_failure_modes():
    from sovereign_agent.tools.git_tools import (
        GitLogTool, GitDiffTool, GitStatusTool, GitShowTool, GitBlameTool,
    )
    for cls in (GitLogTool, GitDiffTool, GitStatusTool, GitShowTool, GitBlameTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


@pytest.mark.asyncio
async def test_git_status_in_real_repo():
    """git_status must succeed when run from inside a git repo."""
    from sovereign_agent.tools.git_tools import GitStatusTool
    tool = GitStatusTool()
    result = await tool.execute(tool.Args(), trace_id="t-status")
    assert result.ok, f"git_status failed: {result.error}"
    assert "branch" in result.metadata


@pytest.mark.asyncio
async def test_git_log_returns_commits():
    """git_log must return at least one commit in this repo."""
    from sovereign_agent.tools.git_tools import GitLogTool
    tool = GitLogTool()
    result = await tool.execute(tool.Args(limit=5), trace_id="t-log")
    assert result.ok, f"git_log failed: {result.error}"
    # Output should contain at least one hash (8 hex chars)
    import re
    assert re.search(r"[0-9a-f]{8}", result.output), "no commit hashes in output"


@pytest.mark.asyncio
async def test_git_diff_working_tree():
    """git_diff with no refs should return the working tree diff (may be empty)."""
    from sovereign_agent.tools.git_tools import GitDiffTool
    tool = GitDiffTool()
    result = await tool.execute(tool.Args(), trace_id="t-diff")
    assert result.ok, f"git_diff failed: {result.error}"


@pytest.mark.asyncio
async def test_git_show_head():
    """git_show HEAD should return the latest commit."""
    from sovereign_agent.tools.git_tools import GitShowTool
    tool = GitShowTool()
    result = await tool.execute(tool.Args(ref="HEAD"), trace_id="t-show")
    assert result.ok, f"git_show failed: {result.error}"
    assert "commit" in result.output.lower() or len(result.output) > 10


@pytest.mark.asyncio
async def test_git_show_invalid_ref():
    """git_show with a bad ref must return ok=False gracefully."""
    from sovereign_agent.tools.git_tools import GitShowTool
    tool = GitShowTool()
    result = await tool.execute(tool.Args(ref="definitely-not-a-real-ref-xyz"), trace_id="t-show-bad")
    assert not result.ok
    assert result.error


@pytest.mark.asyncio
async def test_git_blame_real_file():
    """git_blame on a real file should return line annotations."""
    from sovereign_agent.tools.git_tools import GitBlameTool
    # Use a file we know exists
    repo_root = Path(__file__).resolve()
    for _ in range(8):
        candidate = repo_root.parent / "src" / "sovereign_agent" / "cli.py"
        if candidate.exists():
            break
        repo_root = repo_root.parent
    else:
        pytest.skip("cli.py not found from test directory")

    tool = GitBlameTool()
    result = await tool.execute(
        tool.Args(path=str(candidate), line_start=1, line_end=5),
        trace_id="t-blame",
    )
    assert result.ok, f"git_blame failed: {result.error}"
    assert result.output


@pytest.mark.asyncio
async def test_git_blame_missing_file():
    """git_blame on a missing file must return ok=False gracefully."""
    from sovereign_agent.tools.git_tools import GitBlameTool
    tool = GitBlameTool()
    result = await tool.execute(
        tool.Args(path="/tmp/no-such-file-xyz.py"),
        trace_id="t-blame-bad",
    )
    assert not result.ok


def test_git_helper_survives_non_utf8_output(monkeypatch, tmp_path):
    """Regression test: a real UnicodeDecodeError was found live — a
    non-UTF-8 byte sequence in an ambient historical diff crashed
    git_diff entirely. Root cause: subprocess.run(text=True) with the
    default strict error handler. Fixed via errors="replace"; this proves
    a genuinely non-UTF-8 stdout no longer raises."""
    import subprocess as _subprocess

    from sovereign_agent.tools.git_tools import _git

    class _FakeCompleted:
        returncode = 0
        stdout = "before \udcff after"  # a lone surrogate — what errors="replace"
        # decoding of invalid UTF-8 bytes produces; never raise on this.
        stderr = ""

    def _fake_run(*args, **kwargs):
        assert kwargs.get("errors") == "replace", (
            "git_tools._git must decode with errors='replace' — "
            "a strict decode is exactly what crashed live on a real "
            "non-UTF-8 diff byte sequence"
        )
        return _FakeCompleted()

    monkeypatch.setattr(_subprocess, "run", _fake_run)
    ok, output = _git(["diff"])
    assert ok
    assert "before" in output and "after" in output
