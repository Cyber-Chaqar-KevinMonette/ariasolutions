"""
git_write.py — Tier 2: stage, commit, and branch in git. (FABLE II · M8)

Kevin: *"work safely and efficiently with her git tools — robust and
resilient."* This round's audit found two real gaps, closed here:

  1. GitCommitTool had NO branch check — it would happily commit to
     whatever was checked out, including main/master. Never-main
     discipline: a commit attempted on a default branch auto-branches to
     `aria/<slug>` FIRST — committing to a default branch is refused, not
     discouraged (the refusal never surfaces because the tool resolves it).
  2. The shared `_git()` helper didn't degrade non-UTF-8 bytes
     (`errors="replace"`, already the read-only tools' discipline in
     git_tools.py) — a weird historical blob could crash a write tool.

Safety constraints (non-negotiable, absence not discouragement):
  - No `reset`, no `clean`, no force-push, no `filter-branch`, no branch
    force-delete — these verbs DO NOT EXIST in any tool here, and the
    shared `_git()` helper itself refuses them even if a future bug tried
    (defense in depth, not just "we didn't write it").
  - All T2: operator sees "ok or /cancel" before execution.
  - No push to remote at all (T3 territory; not implemented here).
  - Paths for git_add must be inside the repo root.
  - Branch names validated: only alphanumeric, hyphen, slash, dot, underscore.
  - Garden-aware: when a garden is planted, every git op here must target
    a repo the garden's directory is inside (or that IS the garden) —
    refused otherwise, same wall pathguard already enforces for writes.

Four tools:
  git_add            (T2) — stage one or more files/paths
  git_commit         (T2) — create a commit from staged changes (never-main)
  git_create_branch  (T2) — create and switch to a new branch
  git_checkpoint     (T2) — status → add → commit as ONE gated action
                            (the M7 spirit: fewer approval round-trips)
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

MARK = "git-flow-d"   # provenance marker — this file is a whole-file
                      # replacement (FABLE II M8), not a patch; tests use
                      # this to detect pre- vs post-apply.

_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._/\-]+$")
_SAFE_TIMEOUT = 15

# Absence, not discouragement: no tool in this module ever passes these.
# The shared _git() helper refuses them anyway — a defense-in-depth
# backstop against a future bug, not just a policy on paper.
_FORBIDDEN_VERBS = frozenset({"reset", "clean", "filter-branch", "filter-repo"})
_DEFAULT_BRANCHES = ("main", "master")


class GitFlowError(Exception):
    """Raised by the shared helper when a call is refused before it runs."""


def _git(args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run a git command. Returns (ok, stdout_or_stderr).

    Refuses forbidden verbs and force-flags outright (defense in depth —
    no tool in this module ever passes them, but the helper backstops it
    mechanically). Degrades non-UTF-8 bytes (errors="replace") — a weird
    historical blob must never crash a write tool.
    """
    if args and args[0] in _FORBIDDEN_VERBS:
        return False, f"refused: {args[0]!r} is not a permitted git verb"
    # No tool here ever legitimately needs a force flag — refuse it
    # universally, regardless of subcommand, rather than allowlisting
    # only push/branch (a narrower check a future call could slip past).
    if any(a in ("--force", "-f", "--force-with-lease") for a in args):
        return False, "refused: force flags are not permitted"
    if args and args[0] == "branch" and "-D" in args:
        return False, "refused: branch force-delete is not permitted"
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",  # never let a stray byte crash a write tool
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


def _garden_check(root: Path) -> str | None:
    """None when clear to proceed; an error string when a planted garden
    forbids this repo. A garden must be inside the repo, or the repo must
    be (or be inside) the garden — otherwise git ops here are outside her
    granted ground, the same wall pathguard enforces for file writes."""
    try:
        from sovereign_agent.pathguard import active_garden, is_under
    except Exception:  # noqa: BLE001 — pathguard absent → no garden wall to check
        return None
    garden = active_garden()
    if garden is None:
        return None
    root = root.resolve()
    if is_under(garden, root) or is_under(root, garden) or root == garden:
        return None
    return (f"a garden is planted at {garden} — git ops on {root} are "
            f"outside it (this session's scope: dir: {garden})")


def _current_branch(root: Path) -> str:
    ok, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return out.strip() if ok else ""


def _default_branch_names(root: Path) -> tuple[str, ...]:
    """The names this repo treats as 'default' — main/master plus
    whatever the remote's HEAD actually points at, if resolvable."""
    names = set(_DEFAULT_BRANCHES)
    ok, out = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], root)
    if ok and out:
        names.add(out.rsplit("/", 1)[-1])
    return tuple(names)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, *, max_words: int = 6) -> str:
    words = text.strip().lower().split()[:max_words]
    slug = _SLUG_RE.sub("-", " ".join(words)).strip("-")
    return slug or "work"


def _ensure_not_default_branch(root: Path, *, hint: str) -> tuple[str, str]:
    """Never-main discipline: if HEAD is a default branch, auto-branch to
    `aria/<slug>-<timestamp>` FIRST. Returns (branch_name, note) — note is
    '' when no branching was needed. Committing to a default branch is
    refused, not discouraged: this is why the refusal never surfaces —
    the tool resolves it before the commit ever runs."""
    current = _current_branch(root)
    if current not in _default_branch_names(root):
        return current, ""
    slug = _slugify(hint)
    branch = f"aria/{slug}-{int(time.time())}"
    ok, out = _git(["checkout", "-b", branch], root)
    if not ok:
        raise GitFlowError(f"never-main discipline: on {current!r} and could "
                           f"not auto-branch to {branch!r}: {out}")
    return branch, f"auto-branched from {current!r} (never commits land on a default branch)"


def _format_message(summary: str, body: str) -> str:
    """RESULT-style: one short summary line, blank line, body. Mirrors the
    project's own commit convention (see CLAUDE.md git guidance)."""
    summary = summary.strip()
    body = body.strip()
    return f"{summary}\n\n{body}" if body else summary


# ─── GitAddTool ──────────────────────────────────────────────────────────────


class GitAddTool(Tool):
    """Stage files for the next git commit (Tier 2 — operator confirmation required).

    Stages one or more paths relative to the repo root. All paths must
    be inside the repo root. No glob expansion — each path is validated
    individually. Garden-aware: refused outside a planted garden's repo.

    FAILURE MODES: not_a_git_repo, path_outside_repo, outside_garden, git_error.
    """

    name = "git_add"
    tier = 2
    description = (
        "Stage files for the next git commit. Tier 2 — requires operator confirmation. "
        "Args: paths (list[str] — relative to repo root). "
        "FAILURE MODES: not_a_git_repo, path_outside_repo, outside_garden, git_error."
    )
    failure_modes = ("not_a_git_repo", "path_outside_repo", "outside_garden", "git_error")

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
        garden_err = _garden_check(root)
        if garden_err:
            return ToolResult(ok=False, error=f"outside_garden: {garden_err}")

        validated: list[str] = []
        for p in args.paths:
            ok, result = _resolve_and_validate_path(p, root)
            if not ok:
                return ToolResult(ok=False, error=result)
            validated.append(result)

        ok, out = _git(["add", "--"] + validated, root)
        if not ok:
            return ToolResult(ok=False, error=f"git add failed: {out}")

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

    NEVER-MAIN DISCIPLINE: if HEAD is on a default branch (main/master, or
    whatever the remote's HEAD resolves to), this auto-branches to
    `aria/<slug>` FIRST — the commit always lands on her own branch.

    Commit message should focus on WHY, not what. Requires staged changes
    to exist; never creates empty commits. No amend, no --no-verify, no
    signing bypass.

    FAILURE MODES: not_a_git_repo, outside_garden, nothing_staged, git_error.
    """

    name = "git_commit"
    tier = 2
    description = (
        "Create a git commit from staged changes. Tier 2 — operator confirmation required. "
        "Never lands on a default branch — auto-branches to aria/<slug> first if needed. "
        "Args: message (str — the commit message). "
        "FAILURE MODES: not_a_git_repo, outside_garden, nothing_staged, git_error."
    )
    failure_modes = ("not_a_git_repo", "outside_garden", "nothing_staged", "git_error")

    class Args(BaseModel):
        message: str = Field(description="Commit message. Focus on the why.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.message.strip():
            return ToolResult(ok=False, error="commit message must not be empty")

        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not inside a git repository")
        garden_err = _garden_check(root)
        if garden_err:
            return ToolResult(ok=False, error=f"outside_garden: {garden_err}")

        ok_diff, diff_out = _git(["diff", "--cached", "--name-only"], root)
        if not ok_diff:
            return ToolResult(ok=False, error=f"could not check staged changes: {diff_out}")
        if not diff_out.strip():
            return ToolResult(ok=False, error="nothing staged — use git_add first")

        try:
            branch, branch_note = _ensure_not_default_branch(root, hint=args.message)
        except GitFlowError as exc:
            return ToolResult(ok=False, error=str(exc))

        ok, out = _git(["commit", "-m", args.message.strip()], root)
        if not ok:
            return ToolResult(ok=False, error=f"git commit failed: {out}")

        _, hash_out = _git(["rev-parse", "--short", "HEAD"], root)
        staged_files = [f for f in diff_out.splitlines() if f.strip()]
        header = f"{branch_note}\n" if branch_note else ""
        return ToolResult(
            ok=True,
            output=(
                f"{header}Committed: {hash_out} (branch {branch})\n"
                f"  {args.message.strip().splitlines()[0][:80]}\n"
                f"  {len(staged_files)} file(s) committed"
            ),
            metadata={"commit_hash": hash_out, "files": staged_files,
                     "branch": branch, "auto_branched": bool(branch_note)},
        )


# ─── GitCreateBranchTool ─────────────────────────────────────────────────────


class GitCreateBranchTool(Tool):
    """Create a new git branch and switch to it (Tier 2).

    Creates a branch from an optional starting ref (defaults to HEAD).
    Branch name is validated. No branch deletion, no force creation over
    existing branches.

    FAILURE MODES: not_a_git_repo, outside_garden, invalid_branch_name, branch_exists, git_error.
    """

    name = "git_create_branch"
    tier = 2
    description = (
        "Create a new branch and switch to it. Tier 2 — operator confirmation required. "
        "Args: name (str — branch name), from_ref (str, optional — default HEAD). "
        "FAILURE MODES: not_a_git_repo, outside_garden, invalid_branch_name, branch_exists, git_error."
    )
    failure_modes = ("not_a_git_repo", "outside_garden", "invalid_branch_name",
                     "branch_exists", "git_error")

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
        if name in ("HEAD", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD"):
            return ToolResult(ok=False, error=f"reserved git ref name: {name!r}")

        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not inside a git repository")
        garden_err = _garden_check(root)
        if garden_err:
            return ToolResult(ok=False, error=f"outside_garden: {garden_err}")

        from_ref = args.from_ref.strip() or "HEAD"

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


# ─── GitCheckpointTool ───────────────────────────────────────────────────────


class GitCheckpointTool(Tool):
    """Status → add → commit as ONE gated action (Tier 2).

    The composite the M7 graduated-trust spirit calls for: fewer approval
    round-trips for a routine, low-risk sequence. One operator confirmation
    covers staging the named paths AND committing them — instead of two.

    Refuses on a clean tree (nothing to checkpoint) and on a dirty
    merge/rebase in progress (checkpointing mid-conflict-resolution is
    confusing, not helpful). Same never-main and garden discipline as
    git_commit; message composes RESULT-style (summary + optional body).

    FAILURE MODES: not_a_git_repo, outside_garden, nothing_changed,
    merge_in_progress, path_outside_repo, git_error.
    """

    name = "git_checkpoint"
    tier = 2
    description = (
        "Stage the named paths and commit them as ONE gated action — status, "
        "add, and commit together. Tier 2 — operator confirmation required "
        "(covers the whole checkpoint, not each step). "
        "Args: paths (list[str] — relative to repo root), summary (one-line, "
        "the RESULT-style header), body (optional — the why, in more depth). "
        "Never lands on a default branch — auto-branches to aria/<slug> if needed. "
        "FAILURE MODES: not_a_git_repo, outside_garden, nothing_changed, "
        "merge_in_progress, path_outside_repo, git_error."
    )
    failure_modes = ("not_a_git_repo", "outside_garden", "nothing_changed",
                     "merge_in_progress", "path_outside_repo", "git_error")

    class Args(BaseModel):
        paths: list[str] = Field(
            description="File/directory paths to stage (relative to repo root).")
        summary: str = Field(description="One-line commit summary (the RESULT header).")
        body: str = Field(default="", description="Optional body — the why, in depth.")

    async def execute(self, args: "GitCheckpointTool.Args", *, trace_id: str) -> ToolResult:
        if not args.paths:
            return ToolResult(ok=False, error="paths must not be empty")
        if not args.summary.strip():
            return ToolResult(ok=False, error="summary must not be empty")

        root = _repo_root()
        if root is None:
            return ToolResult(ok=False, error="not inside a git repository")
        garden_err = _garden_check(root)
        if garden_err:
            return ToolResult(ok=False, error=f"outside_garden: {garden_err}")

        # dirty-tree guard: an in-progress merge/rebase/cherry-pick is not a
        # safe moment for a checkpoint commit — resolve that first.
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
            ok_m, _ = _git(["rev-parse", "--verify", "--quiet", marker], root)
            if ok_m:
                return ToolResult(
                    ok=False,
                    error=f"merge_in_progress: {marker} exists — resolve the "
                          f"in-progress operation before checkpointing",
                )
        if (root / ".git" / "rebase-merge").exists() or (root / ".git" / "rebase-apply").exists():
            return ToolResult(ok=False, error="merge_in_progress: a rebase is in progress")

        validated: list[str] = []
        for p in args.paths:
            ok, result = _resolve_and_validate_path(p, root)
            if not ok:
                return ToolResult(ok=False, error=f"path_outside_repo: {result}")
            validated.append(result)

        ok, out = _git(["add", "--"] + validated, root)
        if not ok:
            return ToolResult(ok=False, error=f"git add failed: {out}")

        ok_diff, diff_out = _git(["diff", "--cached", "--name-only"], root)
        if not ok_diff:
            return ToolResult(ok=False, error=f"could not check staged changes: {diff_out}")
        if not diff_out.strip():
            return ToolResult(ok=False, error="nothing_changed: the named paths introduced no diff")

        message = _format_message(args.summary, args.body)
        try:
            branch, branch_note = _ensure_not_default_branch(root, hint=args.summary)
        except GitFlowError as exc:
            return ToolResult(ok=False, error=str(exc))

        ok, out = _git(["commit", "-m", message], root)
        if not ok:
            return ToolResult(ok=False, error=f"git commit failed: {out}")

        _, hash_out = _git(["rev-parse", "--short", "HEAD"], root)
        staged_files = [f for f in diff_out.splitlines() if f.strip()]
        header = f"{branch_note}\n" if branch_note else ""
        return ToolResult(
            ok=True,
            output=(
                f"{header}Checkpointed: {hash_out} (branch {branch})\n"
                f"  {args.summary.strip()[:80]}\n"
                f"  {len(staged_files)} file(s): {', '.join(staged_files[:10])}"
                + (" …" if len(staged_files) > 10 else "")
            ),
            metadata={"commit_hash": hash_out, "files": staged_files,
                     "branch": branch, "auto_branched": bool(branch_note)},
        )
