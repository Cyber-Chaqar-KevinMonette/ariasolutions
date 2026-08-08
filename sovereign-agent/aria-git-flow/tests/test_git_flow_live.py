"""aria-git-flow — safe, efficient git work. (FABLE II · M8)

git_write.py is a WHOLE-FILE replacement (not an anchored patch), so the
staged conftest's extend_paths cannot shadow the still-live old file —
`sovereign_agent.tools.git_write` resolves to the OLD file until the
apply script's `cp` lands. Every behavioral test below checks the MARK
and skips honestly pre-apply; the apply script re-runs this file and
requires zero skips. Real git repos in tmp_path (never the live repo)
via the scratch_repo fixture (conftest.py) + monkeypatch.chdir, restored
per test.
"""
from __future__ import annotations

import inspect
import subprocess

import pytest


@pytest.fixture
def scratch_repo(tmp_path, monkeypatch):
    """A real git repo in tmp_path, on a NON-default branch by default (so
    tests exercise the common case explicitly; never-main tests switch to
    main themselves). Defined here (not conftest.py) so it travels with
    this file when promoted from staged to live tests/."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*a):
        return subprocess.run(["git", *a], cwd=repo, check=True,
                              capture_output=True, text=True)

    # Explicit -b main: init.defaultBranch is unset on this box (git 2.43
    # falls back to 'master' with a warning) — never rely on ambient config
    # for which branch "main" tests can assume exists.
    run("init", "-q", "-b", "main")
    run("config", "user.email", "aria@example.test")
    run("config", "user.name", "Aria Test")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-q", "-m", "initial commit")
    run("checkout", "-q", "-b", "work-branch")
    monkeypatch.chdir(repo)
    return repo


def _new_git_write() -> bool:
    from sovereign_agent.tools import git_write

    return getattr(git_write, "MARK", "") == "git-flow-d"


def _git_tools_patched() -> bool:
    from sovereign_agent.tools import git_tools

    return "git-flow-d" in inspect.getsource(git_tools)


def _run(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()


# ─── the forbidden-verb backstop (absence, not discouragement) ──────────


@pytest.mark.asyncio
async def test_git_helper_refuses_reset_and_clean(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import _git

    ok, out = _git(["reset", "--hard"], scratch_repo)
    assert not ok and "refused" in out
    ok, out = _git(["clean", "-fd"], scratch_repo)
    assert not ok and "refused" in out


@pytest.mark.asyncio
async def test_git_helper_refuses_force_flags(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import _git

    ok, out = _git(["push", "--force"], scratch_repo)
    assert not ok and "refused" in out
    ok, out = _git(["checkout", "-f", "main"], scratch_repo)
    assert not ok and "refused" in out


@pytest.mark.asyncio
async def test_git_helper_refuses_branch_force_delete(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import _git

    ok, out = _git(["branch", "-D", "work-branch"], scratch_repo)
    assert not ok and "refused" in out


@pytest.mark.asyncio
async def test_git_tools_read_only_helper_has_the_same_backstop(scratch_repo):
    if not _git_tools_patched():
        pytest.skip("pre-apply: git_tools.py backstop not yet patched")
    from sovereign_agent.tools.git_tools import _git as read_git

    ok, out = read_git(["reset", "--hard"], scratch_repo)
    assert not ok and "refused" in out


@pytest.mark.asyncio
async def test_forbidden_verbs_never_appear_in_a_real_tool_call(scratch_repo):
    """No tool anywhere in this module ever legitimately calls a forbidden
    verb — confirmed by exercising the normal path end to end."""
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitAddTool, GitCommitTool

    (scratch_repo / "f.txt").write_text("x", encoding="utf-8")
    add = await GitAddTool().execute(GitAddTool.Args(paths=["f.txt"]), trace_id="t")
    assert add.ok
    commit = await GitCommitTool().execute(
        GitCommitTool.Args(message="add f.txt"), trace_id="t")
    assert commit.ok


# ─── errors="replace" resilience ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_git_helper_never_crashes_on_non_utf8_bytes(monkeypatch, scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    import subprocess as sp

    from sovereign_agent.tools import git_write as gw

    class _FakeCompleted:
        returncode = 0
        stdout_bytes = b"clean line\n\xff\xfe garbage \x80 bytes\n"
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = ""

    def _fake_run(*a, **kw):
        assert kw.get("errors") == "replace"
        return _FakeCompleted()

    monkeypatch.setattr(sp, "run", _fake_run)
    ok, out = gw._git(["status"], scratch_repo)
    assert ok and "clean line" in out   # never raised UnicodeDecodeError


# ─── never-main discipline ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_commit_on_main_auto_branches_never_lands_there(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitAddTool, GitCommitTool

    _run(scratch_repo, "checkout", "-q", "main")
    (scratch_repo / "on_main.txt").write_text("x", encoding="utf-8")
    await GitAddTool().execute(GitAddTool.Args(paths=["on_main.txt"]), trace_id="t")
    result = await GitCommitTool().execute(
        GitCommitTool.Args(message="should not land on main"), trace_id="t")
    assert result.ok
    assert result.metadata["auto_branched"] is True
    assert result.metadata["branch"].startswith("aria/")
    assert _run(scratch_repo, "rev-parse", "--abbrev-ref", "HEAD") != "main"
    log_main = _run(scratch_repo, "log", "--oneline", "main")
    assert "should not land on main" not in log_main


@pytest.mark.asyncio
async def test_commit_on_master_auto_branches_too(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitAddTool, GitCommitTool

    _run(scratch_repo, "checkout", "-q", "-b", "master")
    (scratch_repo / "on_master.txt").write_text("x", encoding="utf-8")
    await GitAddTool().execute(GitAddTool.Args(paths=["on_master.txt"]), trace_id="t")
    result = await GitCommitTool().execute(
        GitCommitTool.Args(message="master too"), trace_id="t")
    assert result.ok and result.metadata["auto_branched"] is True


@pytest.mark.asyncio
async def test_commit_on_a_non_default_branch_never_branches(scratch_repo):
    """The common case: already on aria/<slug> or any feature branch —
    commit lands right there, no surprise branching."""
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitAddTool, GitCommitTool

    (scratch_repo / "f2.txt").write_text("x", encoding="utf-8")
    await GitAddTool().execute(GitAddTool.Args(paths=["f2.txt"]), trace_id="t")
    result = await GitCommitTool().execute(
        GitCommitTool.Args(message="normal commit"), trace_id="t")
    assert result.ok
    assert result.metadata["auto_branched"] is False
    assert result.metadata["branch"] == "work-branch"


@pytest.mark.asyncio
async def test_checkpoint_also_honors_never_main(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitCheckpointTool

    _run(scratch_repo, "checkout", "-q", "main")
    (scratch_repo / "cp_on_main.txt").write_text("x", encoding="utf-8")
    result = await GitCheckpointTool().execute(
        GitCheckpointTool.Args(paths=["cp_on_main.txt"], summary="checkpoint on main"),
        trace_id="t")
    assert result.ok
    assert result.metadata["auto_branched"] is True
    assert _run(scratch_repo, "rev-parse", "--abbrev-ref", "HEAD") != "main"


# ─── git_checkpoint: status→add→commit as one gated action ───────────────


@pytest.mark.asyncio
async def test_checkpoint_stages_and_commits_in_one_call(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitCheckpointTool

    (scratch_repo / "a.txt").write_text("a", encoding="utf-8")
    (scratch_repo / "b.txt").write_text("b", encoding="utf-8")
    result = await GitCheckpointTool().execute(
        GitCheckpointTool.Args(paths=["a.txt", "b.txt"], summary="add a and b",
                              body="two files, one gated action"),
        trace_id="t")
    assert result.ok
    assert set(result.metadata["files"]) == {"a.txt", "b.txt"}
    msg = _run(scratch_repo, "log", "-1", "--pretty=%B")
    assert "add a and b" in msg and "two files, one gated action" in msg


@pytest.mark.asyncio
async def test_checkpoint_refuses_when_paths_introduce_no_diff(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitCheckpointTool

    result = await GitCheckpointTool().execute(
        GitCheckpointTool.Args(paths=["README.md"], summary="nothing changed"),
        trace_id="t")
    assert not result.ok and "nothing_changed" in result.error


@pytest.mark.asyncio
async def test_checkpoint_refuses_during_a_merge(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import GitCheckpointTool

    head = _run(scratch_repo, "rev-parse", "HEAD")
    (scratch_repo / ".git" / "MERGE_HEAD").write_text(head + "\n", encoding="utf-8")
    (scratch_repo / "during_merge.txt").write_text("x", encoding="utf-8")
    result = await GitCheckpointTool().execute(
        GitCheckpointTool.Args(paths=["during_merge.txt"], summary="mid merge"),
        trace_id="t")
    assert not result.ok and "merge_in_progress" in result.error


@pytest.mark.asyncio
async def test_checkpoint_message_format_is_result_style():
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.tools.git_write import _format_message

    assert _format_message("summary", "") == "summary"
    assert _format_message("summary", "body text") == "summary\n\nbody text"


# ─── garden-aware ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_git_ops_refused_outside_a_planted_garden(scratch_repo, tmp_path):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.pathguard import clear_garden, set_garden
    from sovereign_agent.tools.git_write import GitAddTool

    other = tmp_path / "elsewhere"
    other.mkdir()
    set_garden(other)
    try:
        (scratch_repo / "gf.txt").write_text("x", encoding="utf-8")
        result = await GitAddTool().execute(GitAddTool.Args(paths=["gf.txt"]),
                                            trace_id="t")
        assert not result.ok and "outside_garden" in result.error
    finally:
        clear_garden()


@pytest.mark.asyncio
async def test_git_ops_allowed_when_garden_is_the_repo(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.pathguard import clear_garden, set_garden
    from sovereign_agent.tools.git_write import GitAddTool

    set_garden(scratch_repo)
    try:
        (scratch_repo / "gf2.txt").write_text("x", encoding="utf-8")
        result = await GitAddTool().execute(GitAddTool.Args(paths=["gf2.txt"]),
                                            trace_id="t")
        assert result.ok
    finally:
        clear_garden()


@pytest.mark.asyncio
async def test_git_ops_allowed_when_no_garden_planted(scratch_repo):
    if not _new_git_write():
        pytest.skip("pre-apply: git_write.py not yet replaced")
    from sovereign_agent.pathguard import active_garden

    assert active_garden() is None   # the default, unplanted state
    from sovereign_agent.tools.git_write import GitAddTool

    (scratch_repo / "gf3.txt").write_text("x", encoding="utf-8")
    result = await GitAddTool().execute(GitAddTool.Args(paths=["gf3.txt"]),
                                        trace_id="t")
    assert result.ok


# ─── existing behavior, unchanged ────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_and_commit_still_work_the_old_way(scratch_repo):
    from sovereign_agent.tools.git_write import GitAddTool, GitCommitTool

    (scratch_repo / "legacy.txt").write_text("x", encoding="utf-8")
    add = await GitAddTool().execute(GitAddTool.Args(paths=["legacy.txt"]), trace_id="t")
    assert add.ok
    commit = await GitCommitTool().execute(
        GitCommitTool.Args(message="legacy path"), trace_id="t")
    assert commit.ok
    assert "commit_hash" in commit.metadata


@pytest.mark.asyncio
async def test_commit_still_refuses_when_nothing_staged(scratch_repo):
    from sovereign_agent.tools.git_write import GitCommitTool

    result = await GitCommitTool().execute(GitCommitTool.Args(message="empty"),
                                           trace_id="t")
    assert not result.ok and "nothing staged" in result.error


@pytest.mark.asyncio
async def test_create_branch_still_validates_names(scratch_repo):
    from sovereign_agent.tools.git_write import GitCreateBranchTool

    result = await GitCreateBranchTool().execute(
        GitCreateBranchTool.Args(name="bad name!"), trace_id="t")
    assert not result.ok and "invalid branch name" in result.error


def test_three_original_tools_registered_at_tier_2():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY

    for name in ("git_add", "git_commit", "git_create_branch"):
        assert name in _TIER_REGISTRY and _TIER_REGISTRY[name].tier == 2


def test_git_checkpoint_registered_once_applied():
    import inspect as _inspect

    from sovereign_agent import tools as tools_pkg

    # tools/__init__.py's anchor is git-flow-import-d (the repo's own
    # "<name>-import-d" convention), not the module-wide MARK.
    if "git-flow-import-d" not in _inspect.getsource(tools_pkg):
        pytest.skip("pre-apply: GitCheckpointTool not yet registered")
    from sovereign_agent.authority import _TIER_REGISTRY

    assert "git_checkpoint" in _TIER_REGISTRY
    assert _TIER_REGISTRY["git_checkpoint"].tier == 2
