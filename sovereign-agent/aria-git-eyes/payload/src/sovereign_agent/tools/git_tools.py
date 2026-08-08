"""
git_tools.py — Tier 0 read-only git insight tools

Five tools that give Aria eyes on the repository history without any write
risk. All tools call `git` via subprocess with no shell=True, 15s timeout,
and graceful fallback when not in a git repo.

  git_log    — recent commits (message, author, hash, date)
  git_diff   — diff between refs or working tree
  git_status — staged / unstaged / untracked state
  git_show   — full content of one specific commit
  git_blame  — line-level authorship for a file
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_GIT_TIMEOUT = 15  # seconds; all git calls hard-capped


def _git(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    """Run a git command. Returns (ok, output_or_error)."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            cwd=cwd or Path.cwd(),
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, (result.stderr or result.stdout or "git exited non-zero").strip()
    except FileNotFoundError:
        return False, "git not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"git timed out after {_GIT_TIMEOUT}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"unexpected error: {exc!r}"


def _repo_root(hint: str | None = None) -> Path | None:
    """Return the git repo root, or None if not in a repo."""
    start = Path(hint).resolve() if hint else Path.cwd()
    ok, out = _git(["rev-parse", "--show-toplevel"], cwd=start)
    if not ok:
        return None
    return Path(out.strip())


# ── GitLogTool ────────────────────────────────────────────────────────────────


class GitLogTool(Tool):
    """Show recent git commit history.

    Call before any code work to understand what changed recently. The output
    shows commit hash, author, date, and the full commit message for each entry.
    Use the `path` argument to limit to commits touching a specific file or directory.
    """

    name = "git_log"
    tier = 0
    description = (
        "Show recent git commit history. "
        "Args: limit (default 20), branch (default HEAD), path (optional file filter). "
        "Returns: one-line-per-commit summary with hash, author, date, subject. "
        "Call before code work to ground reasoning in actual repo state. "
        "FAILURE MODES: not_a_git_repo, git_not_found, timeout."
    )
    failure_modes = ("not_a_git_repo", "git_not_found", "timeout", "git_error")

    class Args(BaseModel):
        limit: int = Field(default=20, ge=1, le=200, description="Max commits to return.")
        branch: str = Field(default="HEAD", description="Branch or ref to log.")
        path: str = Field(default="", description="Limit to commits touching this path (optional).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not in a git repository")

        fmt = "%H%x09%an%x09%ad%x09%s"  # hash TAB author TAB date TAB subject
        cmd = ["log", f"--max-count={args.limit}", f"--pretty=format:{fmt}",
               "--date=short", args.branch]
        if args.path:
            cmd += ["--", args.path]

        ok, out = _git(cmd, cwd=root)
        if not ok:
            return ToolResult(ok=False, error=out)

        lines = [ln for ln in out.splitlines() if ln.strip()]
        rows = []
        for ln in lines:
            parts = ln.split("\t", 3)
            if len(parts) == 4:
                h, author, date, subject = parts
                rows.append(f"{h[:8]}  {date}  {author:<20s}  {subject}")
            else:
                rows.append(ln)

        output = "\n".join(rows) if rows else "(no commits found)"
        return ToolResult(
            ok=True,
            output=output,
            metadata={"root": str(root), "count": len(rows), "branch": args.branch},
        )


# ── GitDiffTool ───────────────────────────────────────────────────────────────


class GitDiffTool(Tool):
    """Show a git diff — between commits, or the working tree.

    Omit both ref_a and ref_b to see unstaged working-tree changes.
    Set ref_a=HEAD to see staged changes. Set both refs to compare commits.
    Use `path` to limit the diff to a specific file or directory.
    """

    name = "git_diff"
    tier = 0
    description = (
        "Show a git diff. "
        "Args: ref_a (optional), ref_b (optional), path (optional file filter), "
        "max_lines (default 500). "
        "Leave both refs empty for working-tree diff. Set ref_a=HEAD for staged diff. "
        "FAILURE MODES: not_a_git_repo, invalid_ref, timeout, output_truncated."
    )
    failure_modes = ("not_a_git_repo", "invalid_ref", "git_not_found", "timeout", "output_truncated")

    class Args(BaseModel):
        ref_a: str = Field(default="", description="First ref (empty = working tree diff).")
        ref_b: str = Field(default="", description="Second ref (empty = compare ref_a to working tree).")
        path: str = Field(default="", description="Limit diff to this path (optional).")
        max_lines: int = Field(default=500, ge=10, le=5000, description="Truncate output at this many lines.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not in a git repository")

        cmd = ["diff"]
        if args.ref_a and args.ref_b:
            cmd += [args.ref_a, args.ref_b]
        elif args.ref_a:
            cmd += [args.ref_a]
        # else: working tree diff (no refs)

        if args.path:
            cmd += ["--", args.path]

        ok, out = _git(cmd, cwd=root)
        if not ok:
            return ToolResult(ok=False, error=out)

        lines = out.splitlines()
        truncated = len(lines) > args.max_lines
        if truncated:
            lines = lines[: args.max_lines]
            lines.append(f"\n... (truncated at {args.max_lines} lines)")

        return ToolResult(
            ok=True,
            output="\n".join(lines) if lines else "(no changes)",
            metadata={"root": str(root), "truncated": truncated, "line_count": len(lines)},
        )


# ── GitStatusTool ─────────────────────────────────────────────────────────────


class GitStatusTool(Tool):
    """Show the git working tree status — staged, unstaged, and untracked files.

    Call at the start of any coding session to understand the current state.
    Returns a compact machine-readable summary plus the full `git status` output.
    """

    name = "git_status"
    tier = 0
    description = (
        "Show the git working tree status (staged, unstaged, untracked). "
        "No args needed. Returns: a structured summary + full status output. "
        "Call before any code work to know the current working tree state. "
        "FAILURE MODES: not_a_git_repo, git_not_found, timeout."
    )
    failure_modes = ("not_a_git_repo", "git_not_found", "timeout")

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not in a git repository")

        # Machine-readable porcelain
        ok_p, porcelain = _git(["status", "--porcelain=v1"], cwd=root)
        if not ok_p:
            return ToolResult(ok=False, error=porcelain)

        # Human-readable
        ok_h, human = _git(["status", "--short", "--branch"], cwd=root)
        if not ok_h:
            human = porcelain  # fallback

        # Parse porcelain for summary
        staged, unstaged, untracked = [], [], []
        for ln in porcelain.splitlines():
            if len(ln) < 2:
                continue
            xy, name = ln[:2], ln[3:]
            if xy[0] != " " and xy[0] != "?":
                staged.append(name)
            if xy[1] not in (" ", "?"):
                unstaged.append(name)
            if xy == "??":
                untracked.append(name)

        summary = {
            "staged": len(staged),
            "unstaged": len(unstaged),
            "untracked": len(untracked),
            "clean": not staged and not unstaged,
        }

        # Branch name
        ok_b, branch_raw = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        branch = branch_raw.strip() if ok_b else "unknown"

        output = human.strip() if human.strip() else "(working tree clean)"
        return ToolResult(
            ok=True,
            output=output,
            metadata={"root": str(root), "branch": branch, "summary": summary},
        )


# ── GitShowTool ───────────────────────────────────────────────────────────────


class GitShowTool(Tool):
    """Show the full content of a specific git commit.

    Returns the commit metadata (author, date, message) and the full diff
    introduced by that commit. Useful for understanding exactly what a specific
    change did.
    """

    name = "git_show"
    tier = 0
    description = (
        "Show the full content of a specific git commit: metadata + diff. "
        "Args: ref (commit hash, tag, or branch name), max_lines (default 400). "
        "FAILURE MODES: not_a_git_repo, invalid_ref, timeout, output_truncated."
    )
    failure_modes = ("not_a_git_repo", "invalid_ref", "git_not_found", "timeout", "output_truncated")

    class Args(BaseModel):
        ref: str = Field(description="Commit hash (short or full), tag, or branch.")
        max_lines: int = Field(default=400, ge=10, le=3000)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not in a git repository")

        ok, out = _git(["show", args.ref], cwd=root)
        if not ok:
            return ToolResult(ok=False, error=f"invalid ref {args.ref!r}: {out}")

        lines = out.splitlines()
        truncated = len(lines) > args.max_lines
        if truncated:
            lines = lines[: args.max_lines]
            lines.append(f"\n... (truncated at {args.max_lines} lines)")

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            metadata={"root": str(root), "ref": args.ref, "truncated": truncated},
        )


# ── GitBlameTool ──────────────────────────────────────────────────────────────


class GitBlameTool(Tool):
    """Show who last changed each line of a file (git blame).

    Useful for understanding authorship, when a line was introduced, and in
    which commit. Use line_start and line_end to focus on a specific range.
    """

    name = "git_blame"
    tier = 0
    description = (
        "Show line-level authorship for a file (git blame). "
        "Args: path (required), line_start (optional), line_end (optional), max_lines (default 200). "
        "Returns: each line annotated with commit hash, author, date, and content. "
        "FAILURE MODES: not_a_git_repo, file_not_found, not_tracked, timeout, output_truncated."
    )
    failure_modes = (
        "not_a_git_repo", "file_not_found", "not_tracked",
        "git_not_found", "timeout", "output_truncated",
    )

    class Args(BaseModel):
        path: str = Field(description="Path to the file to blame.")
        line_start: Optional[int] = Field(default=None, ge=1, description="First line (1-indexed, optional).")
        line_end: Optional[int] = Field(default=None, ge=1, description="Last line (1-indexed, optional).")
        max_lines: int = Field(default=200, ge=10, le=1000)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not in a git repository")

        p = Path(args.path).expanduser()
        if not p.exists():
            return ToolResult(ok=False, error=f"file not found: {p}")

        cmd = ["blame", "--line-porcelain"]
        if args.line_start and args.line_end:
            cmd += [f"-L{args.line_start},{args.line_end}"]
        elif args.line_start:
            cmd += [f"-L{args.line_start},"]

        cmd.append(str(p))
        ok, out = _git(cmd, cwd=root)
        if not ok:
            return ToolResult(ok=False, error=out)

        # Parse porcelain blame into human-readable
        lines_out = []
        current: dict[str, str] = {}
        for ln in out.splitlines():
            if ln.startswith("\t"):
                content = ln[1:]
                h = current.get("hash", "?")[:8]
                author = current.get("author", "?")[:20]
                ts = current.get("author-time", "")[:10]
                lineno = current.get("lineno", "?")
                lines_out.append(f"{lineno:>5} {h} {ts} {author:<20} {content}")
                current = {}
            else:
                parts = ln.split(" ", 3)
                if len(parts[0]) == 40:
                    current["hash"] = parts[0]
                    if len(parts) >= 3:
                        current["lineno"] = parts[2]
                elif ln.startswith("author "):
                    current["author"] = ln[7:]
                elif ln.startswith("author-time "):
                    import datetime
                    try:
                        ts = int(ln[12:])
                        current["author-time"] = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
                    except (ValueError, OSError):
                        current["author-time"] = ln[12:]

        truncated = len(lines_out) > args.max_lines
        if truncated:
            lines_out = lines_out[: args.max_lines]
            lines_out.append(f"\n... (truncated at {args.max_lines} lines)")

        output = "\n".join(lines_out) if lines_out else "(no blame output)"
        return ToolResult(
            ok=True,
            output=output,
            metadata={"root": str(root), "path": str(p), "truncated": truncated},
        )
