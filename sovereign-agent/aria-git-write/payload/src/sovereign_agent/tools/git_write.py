"""
git_write.py — Tier 2: stage, commit, and branch in git

Aria helps build Aria. When she creates an aria-<name>/ module, she
should be able to stage and commit it — with operator confirmation (T2).

Safety constraints (non-negotiable):
  - All T2: operator sees "ok or /cancel" before execution
  - No force-push (ever)
  - No push to remote (T3 would be required; not implemented here)
  - No rebase, reset, or branch deletion
  - Paths for git_add must be inside the repo root
  - Branch names validated: only alphanumeric, hyphen, slash, dot, underscore

Three tools:
  git_add    (T2) — stage one or more files/paths
  git_commit (T2) — create a commit from staged changes
  git_create_branch (T2) — create and switch to a new branch
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._/\-]+$")
_SAFE_TIMEOUT = 15


def _git(args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run a git command. Returns (ok, stdout_or_stderr)."""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_SAFE_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode == 0:
            return True, (r.stdout or "").strip()
        return False, (r.stderr or r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return False, "git command timed out"
    except FileNotFoundError:
        return False, "git not found in PATH"
    except Exception as exc:  # noqa: BLE001
        return False, f"subprocess error: {exc!r}"


def _repo_root(hint: Path | None = None) -> Path | None:
    """Walk up from hint (or cwd) to find the git repo root."""
    cwd = hint or Path.cwd()
    ok, out = _git(["rev-parse", "--show-toplevel"], cwd)
    if ok and out:
        return Path(out)
    return None


def _resolve_and_validate_path(p: str, root: Path) -> tuple[bool, str]:
    """Resolve a path and ensure it's inside the repo root."""
    try:
        resolved = (root / p).resolve()
    except Exception:
        return False, f"invalid path: {p!r}"
    try:
        resolved.relative_to(root)
    except ValueError:
        return False, f"path {p!r} is outside repo root {root}"
    return True, str(resolved.relative_to(root))


# ─── GitAddTool ──────────────────────────────────────────────────────────────


class GitAddTool(Tool):
    """Stage files for the next git commit (Tier 2 — operator confirmation required).

    Stages one or more paths relative to the repo root. All paths must
    be inside the repo root. No glob expansion — each path is validated
    individually.

    Aria should propose what to stage and wait for operator approval before
    this runs. The staged set is shown by git_status (T0).

    Args:
      paths — list of file/directory paths to stage (relative to repo root)

    FAILURE MODES: not_a_git_repo, path_outside_repo, git_error.
    """

    name = "git_add"
    tier = 2
    description = (
        "Stage files for the next git commit. Tier 2 — requires operator confirmation. "
        "Args: paths (list[str] — relative to repo root). "
        "FAILURE MODES: not_a_git_repo, path_outside_repo, git_error."
    )
    failure_modes = ("not_a_git_repo", "path_outside_repo", "git_error")

    class Args(BaseModel):
        paths: list[str] = Field(
            description="File/directory paths to stage (relative to repo root).",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.paths:
            return ToolResult(ok=False, error="paths must not be empty")

        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not inside a git repository")

        # Validate all paths first
        validated: list[str] = []
        for p in args.paths:
            ok, result = _resolve_and_validate_path(p, root)
            if not ok:
                return ToolResult(ok=False, error=result)
            validated.append(result)

        ok, out = _git(["add", "--"] + validated, root)
        if not ok:
            return ToolResult(ok=False, error=f"git add failed: {out}")

        # Show what's staged now
        _, status_out = _git(["diff", "--cached", "--stat"], root)
        return ToolResult(
            ok=True,
            output=(
                f"Staged {len(validated)} path(s):\n"
                + "\n".join(f"  + {p}" for p in validated)
                + (f"\n\nStaged changes:\n{status_out}" if status_out else "")
            ),
            metadata={"staged": validated, "root": str(root)},
        )


# ─── GitCommitTool ───────────────────────────────────────────────────────────


class GitCommitTool(Tool):
    """Create a git commit from currently staged changes (Tier 2).

    Commit message should focus on WHY, not what. The commit includes
    all currently staged changes (those added with git_add).

    Safety: requires staged changes to exist. Will not create empty commits.
    No amend, no --no-verify, no signing bypass.

    Args:
      message — commit message (required)

    FAILURE MODES: not_a_git_repo, nothing_staged, git_error.
    """

    name = "git_commit"
    tier = 2
    description = (
        "Create a git commit from staged changes. Tier 2 — operator confirmation required. "
        "Args: message (str — the commit message). "
        "FAILURE MODES: not_a_git_repo, nothing_staged, git_error."
    )
    failure_modes = ("not_a_git_repo", "nothing_staged", "git_error")

    class Args(BaseModel):
        message: str = Field(description="Commit message. Focus on the why.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.message.strip():
            return ToolResult(ok=False, error="commit message must not be empty")

        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not inside a git repository")

        # Check there are staged changes
        ok_diff, diff_out = _git(["diff", "--cached", "--name-only"], root)
        if not ok_diff:
            return ToolResult(ok=False, error=f"could not check staged changes: {diff_out}")
        if not diff_out.strip():
            return ToolResult(ok=False, error="nothing staged — use git_add first")

        ok, out = _git(["commit", "-m", args.message.strip()], root)
        if not ok:
            return ToolResult(ok=False, error=f"git commit failed: {out}")

        # Get the new commit hash
        _, hash_out = _git(["rev-parse", "--short", "HEAD"], root)

        staged_files = [f for f in diff_out.splitlines() if f.strip()]
        return ToolResult(
            ok=True,
            output=(
                f"Committed: {hash_out}\n"
                f"  {args.message.strip()[:80]}\n"
                f"  {len(staged_files)} file(s) committed"
            ),
            metadata={"commit_hash": hash_out, "files": staged_files},
        )


# ─── GitCreateBranchTool ─────────────────────────────────────────────────────


class GitCreateBranchTool(Tool):
    """Create a new git branch and switch to it (Tier 2).

    Creates a branch from an optional starting ref (defaults to HEAD).
    Branch name is validated — only alphanumeric, hyphens, slashes, dots,
    and underscores.

    No branch deletion. No force creation over existing branches.

    Args:
      name     — branch name (validated)
      from_ref — starting ref (default: HEAD)

    FAILURE MODES: not_a_git_repo, invalid_branch_name, branch_exists, git_error.
    """

    name = "git_create_branch"
    tier = 2
    description = (
        "Create a new branch and switch to it. Tier 2 — operator confirmation required. "
        "Args: name (str — branch name), from_ref (str, optional — default HEAD). "
        "FAILURE MODES: not_a_git_repo, invalid_branch_name, branch_exists, git_error."
    )
    failure_modes = ("not_a_git_repo", "invalid_branch_name", "branch_exists", "git_error")

    class Args(BaseModel):
        name: str = Field(description="Branch name (alphanumeric, hyphens, slashes, dots).")
        from_ref: str = Field(default="", description="Starting ref (default: HEAD).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        name = args.name.strip()
        if not name:
            return ToolResult(ok=False, error="branch name must not be empty")
        if not _BRANCH_RE.match(name):
            return ToolResult(
                ok=False,
                error=f"invalid branch name {name!r} — only alphanumeric, hyphens, slashes, dots, underscores",
            )
        # Safety: block obviously dangerous names
        if name in ("HEAD", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD"):
            return ToolResult(ok=False, error=f"reserved git ref name: {name!r}")

        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not inside a git repository")

        from_ref = args.from_ref.strip() or "HEAD"

        # Check branch doesn't already exist
        ok_check, check_out = _git(["rev-parse", "--verify", f"refs/heads/{name}"], root)
        if ok_check:
            return ToolResult(
                ok=False,
                error=f"branch {name!r} already exists — switch to it with 'git checkout {name}'",
            )

        ok, out = _git(["checkout", "-b", name, from_ref], root)
        if not ok:
            return ToolResult(ok=False, error=f"git checkout -b failed: {out}")

        return ToolResult(
            ok=True,
            output=f"Branch created and switched: {name}\n  from: {from_ref}",
            metadata={"branch": name, "from_ref": from_ref},
        )
