"""
tools/command_master.py — Enhanced command execution (M31)

Two Tier 1 tools that give Aria full dev-toolchain access:

  run_command(argv, cwd, timeout, env_extra)
    Like run_shell but with the full expanded allowlist. 16KB output cap.
    Emits command-output-d events with stdout chunks. Returns exit_code,
    stdout, stderr, succeeded.

  edit_in_place(path, old_text, new_text)
    Surgical text replacement in files scoped to repo root or sandbox.
    Validates path is within allowed root, does exact string match + replace,
    returns a diff of what changed.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_OUTPUT_CAP = 16 * 1024  # 16KB

# Expanded T1 allowlist — full dev toolchain
COMMAND_ALLOWLIST: frozenset[str] = frozenset({
    # Python toolchain
    "python", "python3", "pip", "pip3", "uv", "uvicorn",
    "pytest", "ruff", "mypy", "black", "isort", "pyright",
    # Build tools
    "make", "cmake", "ninja", "cargo", "rustc",
    # Node
    "node", "npm", "npx", "yarn", "pnpm", "bun",
    # File ops
    "ls", "ll", "la", "find", "tree",
    "cat", "head", "tail", "wc", "stat",
    "cp", "mv", "mkdir", "touch", "ln",
    "tar", "gzip", "gunzip", "zip", "unzip",
    # Text processing
    "grep", "egrep", "fgrep", "rg", "awk", "sed",
    "sort", "uniq", "cut", "tr", "tee", "xargs",
    "jq", "yq", "diff", "patch",
    # Version control
    "git",
    # Network (safe read-only)
    "curl", "wget",
    # System info
    "df", "du", "ps", "env", "which", "type", "file",
    "echo", "printf",
})

_METACHAR_RE = __import__("re").compile(r"[|;&<>`$\\]")


def _repo_root() -> Path:
    """Walk up from cwd to find repo root (has .venv or pyproject.toml)."""
    p = Path.cwd()
    for _ in range(12):
        if (p / ".venv").exists() or (p / "pyproject.toml").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path.cwd()


def _allowed_roots() -> list[Path]:
    """Paths edit_in_place is allowed to write within."""
    from sovereign_agent.config import SETTINGS
    roots = [_repo_root()]
    try:
        roots.append(SETTINGS.paths.sandbox_dir)
    except Exception:  # noqa: BLE001
        pass
    return roots


class RunCommandTool(Tool):
    """Run a whitelisted command from the expanded dev-toolchain allowlist.

    Covers Python, Node, Git, make, rg, jq, awk, sed, curl, and 40+ others.
    Output is capped at 16KB. Returns exit_code, stdout, stderr, succeeded.

    Use this for dev-cycle operations: lint → test → build → inspect.
    It is not a shell — no pipes, no redirects, no metacharacters.
    """

    name = "run_command"
    tier = 1
    description = (
        "Run a command from the expanded dev-toolchain allowlist (40+ tools). "
        "Args: argv (list starting with command name), cwd (optional path), "
        "timeout (seconds, default 60), env_extra (dict, optional). "
        "Returns: exit_code, stdout, stderr, succeeded. Output capped at 16KB. "
        "No shell metacharacters (pipes, redirects) — just argv."
    )
    failure_modes = (
        "command not in allowlist",
        "metacharacter in argument",
        "timeout exceeded",
        "cwd does not exist",
    )

    class Args(BaseModel):
        argv: list[str] = Field(min_length=1, description="Command + arguments as a list.")
        cwd: Optional[str] = Field(default=None, description="Working directory (absolute path).")
        timeout: int = Field(default=60, ge=1, le=300, description="Timeout in seconds.")
        env_extra: Optional[dict[str, str]] = Field(
            default=None, description="Extra environment variables to merge."
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.events import emit_event

        cmd = args.argv[0]
        if cmd not in COMMAND_ALLOWLIST:
            return ToolResult(
                ok=False,
                error=(
                    f"command {cmd!r} is not in the allowlist. "
                    f"Allowed: {', '.join(sorted(COMMAND_ALLOWLIST))}"
                ),
            )

        for arg in args.argv[1:]:
            if _METACHAR_RE.search(arg):
                return ToolResult(
                    ok=False,
                    error=f"shell metacharacter in argument: {arg!r}",
                )

        cwd = Path(args.cwd) if args.cwd else _repo_root()
        if not cwd.exists():
            return ToolResult(ok=False, error=f"cwd does not exist: {cwd}")

        env = os.environ.copy()
        if args.env_extra:
            env.update(args.env_extra)

        emit_event("command-output-d", plane="agent", trace_id=trace_id, payload={
            "command": args.argv, "cwd": str(cwd),
        })

        try:
            proc = subprocess.run(
                args.argv,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=args.timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                ok=False,
                error=f"command timed out after {args.timeout}s: {' '.join(args.argv)}",
            )
        except FileNotFoundError:
            return ToolResult(ok=False, error=f"command not found: {cmd!r}")

        stdout = proc.stdout[:_OUTPUT_CAP]
        stderr = proc.stderr[:_OUTPUT_CAP // 4]
        succeeded = proc.returncode == 0

        if len(proc.stdout) > _OUTPUT_CAP:
            stdout += f"\n... [truncated at 16KB, total {len(proc.stdout)} bytes] ..."

        return ToolResult(
            ok=True,
            output={
                "exit_code": proc.returncode,
                "succeeded": succeeded,
                "stdout": stdout,
                "stderr": stderr,
                "command": " ".join(args.argv),
            },
            metadata={"exit_code": proc.returncode, "succeeded": succeeded},
        )


class EditInPlaceTool(Tool):
    """Surgical text replacement in a file, scoped to repo root or sandbox.

    Finds old_text in the file and replaces it with new_text. Validates:
      1. Path is within repo root or sandbox (no system files)
      2. old_text exists exactly once in the file (no ambiguous replacements)
      3. File exists and is readable

    Returns a diff showing what changed.
    """

    name = "edit_in_place"
    tier = 1
    description = (
        "Surgical exact-string replacement in a file (scoped to repo root or sandbox). "
        "Args: path (absolute), old_text, new_text. "
        "Returns diff of the change. Fails if old_text not found or ambiguous. "
        "Never edits system files — only repo or sandbox paths."
    )
    failure_modes = (
        "path outside allowed roots",
        "file not found",
        "old_text not found in file",
        "old_text appears more than once (ambiguous)",
    )

    class Args(BaseModel):
        path: str = Field(description="Absolute path to file to edit.")
        old_text: str = Field(description="Exact text to find and replace.")
        new_text: str = Field(description="Replacement text.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        import difflib

        p = Path(args.path)
        if not p.is_absolute():
            return ToolResult(ok=False, error=f"path must be absolute: {args.path!r}")

        allowed = _allowed_roots()
        if not any(_is_within(p, root) for root in allowed):
            return ToolResult(
                ok=False,
                error=(
                    f"path {p} is outside allowed roots. "
                    f"Allowed: {[str(r) for r in allowed]}"
                ),
            )

        if not p.exists():
            return ToolResult(ok=False, error=f"file not found: {p}")

        content = p.read_text(encoding="utf-8", errors="replace")

        count = content.count(args.old_text)
        if count == 0:
            return ToolResult(ok=False, error="old_text not found in file")
        if count > 1:
            return ToolResult(
                ok=False,
                error=f"old_text appears {count} times — too ambiguous. Add more context.",
            )

        new_content = content.replace(args.old_text, args.new_text, 1)
        p.write_text(new_content, encoding="utf-8")

        diff = "".join(difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}",
            n=3,
        ))[:4096]

        return ToolResult(
            ok=True,
            output={
                "path": str(p),
                "diff": diff,
                "lines_before": content.count("\n"),
                "lines_after": new_content.count("\n"),
            },
            metadata={"path": str(p)},
        )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
