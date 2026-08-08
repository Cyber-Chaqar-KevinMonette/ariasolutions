"""
test_git_write.py — Tests for T2 git write tools (M25).
"""
from __future__ import annotations
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    for name in ("git_add", "git_commit", "git_create_branch"):
        assert name in _TIER_REGISTRY, f"{name} not registered"
        assert _TIER_REGISTRY[name].tier == 2, f"{name} must be Tier 2"


def test_failure_modes():
    from sovereign_agent.tools.git_write import GitAddTool, GitCommitTool, GitCreateBranchTool
    assert GitAddTool.failure_modes
    assert GitCommitTool.failure_modes
    assert GitCreateBranchTool.failure_modes


def test_branch_name_validation():
    from sovereign_agent.tools.git_write import _BRANCH_RE
    assert _BRANCH_RE.match("feature/my-branch")
    assert _BRANCH_RE.match("claude/fix-123")
    assert _BRANCH_RE.match("aria.v2")
    assert not _BRANCH_RE.match("bad branch!")
    assert not _BRANCH_RE.match("no spaces")
    assert not _BRANCH_RE.match("no;semicolons")


@pytest.mark.asyncio
async def test_git_add_empty_paths_fails():
    from sovereign_agent.tools.git_write import GitAddTool
    tool = GitAddTool()
    result = await tool.execute(tool.Args(paths=[]), trace_id="t1")
    assert not result.ok
    assert "empty" in result.error


@pytest.mark.asyncio
async def test_git_add_not_in_repo():
    from sovereign_agent.tools.git_write import GitAddTool

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=None):
        tool = GitAddTool()
        result = await tool.execute(tool.Args(paths=["README.md"]), trace_id="t1")
    assert not result.ok
    assert "git repository" in result.error


@pytest.mark.asyncio
async def test_git_add_path_outside_repo(tmp_path):
    from sovereign_agent.tools.git_write import GitAddTool

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=repo_root):
        tool = GitAddTool()
        result = await tool.execute(
            tool.Args(paths=["../../etc/passwd"]),
            trace_id="t1",
        )
    assert not result.ok
    assert "outside" in result.error


@pytest.mark.asyncio
async def test_git_add_success_in_real_repo():
    """Test git_add in the actual repo (staging a file that already exists)."""
    from sovereign_agent.tools.git_write import GitAddTool, _repo_root

    root = _repo_root()
    if root is None:
        pytest.skip("not in a git repo")

    # Mock _repo_root to avoid consuming _git calls, then mock _git for the operations
    with patch("sovereign_agent.tools.git_write._repo_root", return_value=root):
        with patch("sovereign_agent.tools.git_write._git") as mock_git:
            mock_git.side_effect = [
                (True, ""),    # git add
                (True, "README.md | 0"),  # git diff --cached --stat
            ]
            tool = GitAddTool()
            result = await tool.execute(tool.Args(paths=["README.md"]), trace_id="t1")

    assert result.ok
    assert "README.md" in result.output


@pytest.mark.asyncio
async def test_git_commit_empty_message_fails():
    from sovereign_agent.tools.git_write import GitCommitTool
    tool = GitCommitTool()
    result = await tool.execute(tool.Args(message=""), trace_id="t1")
    assert not result.ok


@pytest.mark.asyncio
async def test_git_commit_nothing_staged():
    from sovereign_agent.tools.git_write import GitCommitTool

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=Path("/tmp/repo")):
        with patch("sovereign_agent.tools.git_write._git") as mock_git:
            # git diff --cached --name-only returns empty
            mock_git.return_value = (True, "")
            tool = GitCommitTool()
            result = await tool.execute(tool.Args(message="my commit"), trace_id="t1")

    assert not result.ok
    assert "nothing staged" in result.error


@pytest.mark.asyncio
async def test_git_commit_success():
    from sovereign_agent.tools.git_write import GitCommitTool

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=Path("/tmp/repo")):
        with patch("sovereign_agent.tools.git_write._git") as mock_git:
            mock_git.side_effect = [
                (True, "file.py"),         # git diff --cached --name-only
                (True, "work-branch"),     # git rev-parse --abbrev-ref HEAD (never-main-d check)
                (False, ""),               # git symbolic-ref refs/remotes/origin/HEAD (no remote)
                (True, "[main abc1234]"),   # git commit
                (True, "abc1234"),          # git rev-parse --short HEAD
            ]
            tool = GitCommitTool()
            result = await tool.execute(
                tool.Args(message="add feature X for clarity"),
                trace_id="t1",
            )

    assert result.ok, result.error
    assert "abc1234" in result.output
    assert result.metadata["commit_hash"] == "abc1234"


@pytest.mark.asyncio
async def test_git_create_branch_validates_name():
    from sovereign_agent.tools.git_write import GitCreateBranchTool

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=Path("/tmp/repo")):
        tool = GitCreateBranchTool()
        r1 = await tool.execute(tool.Args(name="bad name!"), trace_id="t1")
        r2 = await tool.execute(tool.Args(name="HEAD"), trace_id="t2")
        r3 = await tool.execute(tool.Args(name=""), trace_id="t3")

    assert not r1.ok
    assert not r2.ok
    assert not r3.ok


@pytest.mark.asyncio
async def test_git_create_branch_success():
    from sovereign_agent.tools.git_write import GitCreateBranchTool

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=Path("/tmp/repo")):
        with patch("sovereign_agent.tools.git_write._git") as mock_git:
            mock_git.side_effect = [
                (False, ""),    # rev-parse verify — branch doesn't exist
                (True, "Switched to a new branch 'feature/test'"),  # checkout -b
            ]
            tool = GitCreateBranchTool()
            result = await tool.execute(
                tool.Args(name="feature/test", from_ref="main"),
                trace_id="t1",
            )

    assert result.ok, result.error
    assert "feature/test" in result.output
    assert result.metadata["branch"] == "feature/test"


@pytest.mark.asyncio
async def test_git_create_branch_already_exists():
    from sovereign_agent.tools.git_write import GitCreateBranchTool

    with patch("sovereign_agent.tools.git_write._repo_root", return_value=Path("/tmp/repo")):
        with patch("sovereign_agent.tools.git_write._git") as mock_git:
            mock_git.return_value = (True, "abc123")  # branch exists
            tool = GitCreateBranchTool()
            result = await tool.execute(
                tool.Args(name="main"),
                trace_id="t1",
            )

    assert not result.ok
    assert "already exists" in result.error
