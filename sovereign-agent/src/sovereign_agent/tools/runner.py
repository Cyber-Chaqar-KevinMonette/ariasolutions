"""
runner.py — Tier 1 code execution sandbox

Closes RISK-012 from the weakness register: Aria writes code but has no way
to run it or verify it works. This module provides three tools:

  run_code   — execute a Python snippet in the project venv
  run_shell  — execute a command from a hardcoded allowlist
  run_tests  — convenience wrapper: pytest with sensible defaults

SAFETY CONSTRAINTS (belt-and-suspenders):

  • All tools are Tier 1 — path-scope enforcement is applied by the loop.
  • run_code: uses .venv/bin/python, never system Python; stdin closed;
    timeout enforced; no shell=True.
  • run_shell: command must be in SHELL_ALLOWLIST (hardcoded, no override);
    no shell metacharacters permitted in args; cwd must be sandbox or repo root.
  • run_tests: thin wrapper around run_shell("pytest"); returns pass/fail counts.
  • All tools: never raise; return ToolResult(ok=False, error=...) on any failure.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

_TIMEOUT_DEFAULT = 30  # seconds
_OUTPUT_CAP = 4000     # chars; protect context window

# Commands that may be run via run_shell. This is the ONLY place they're defined.
SHELL_ALLOWLIST: frozenset[str] = frozenset({  # command-master-runner-d
    # Core Python toolchain
    "pytest", "ruff", "mypy", "black", "isort",
    "python", "python3", "pip", "pip3", "uv",
    # File inspection
    "ls", "find", "tree", "cat", "head", "tail",
    "wc", "diff", "stat", "echo", "file",
    # Text processing
    "grep", "egrep", "fgrep", "rg", "awk", "sed",
    "sort", "uniq", "cut", "jq",
    # Git
    "git",
})

_METACHAR = re.compile(r"[|;&<>`$\\]")


def _find_venv_python(repo_root: Path) -> Path | None:
    """Find the project venv Python. Never system Python."""
    for candidate in (
        repo_root / ".venv" / "bin" / "python",
        repo_root / ".venv" / "bin" / "python3",
        repo_root / "venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return None


def _find_venv_cmd(repo_root: Path, cmd: str) -> Path | None:
    """Find a command in the project venv bin/."""
    for d in (repo_root / ".venv" / "bin", repo_root / "venv" / "bin"):
        p = d / cmd
        if p.exists():
            return p
    return None


def _repo_root() -> Path:
    """Walk up from cwd to find the repo root (has .venv or pyproject.toml)."""
    p = Path.cwd()
    for _ in range(10):
        if (p / ".venv").exists() or (p / "pyproject.toml").exists():
            return p
        parent = p.parent
        if parent == p:
            break
        p = parent
    return Path.cwd()


def _validate_cwd(cwd: str | None, root: Path) -> Path | None:
    """Validate that a proposed cwd is inside the repo root or sandbox."""
    if not cwd:
        return root
    p = Path(cwd).expanduser().resolve()
    # Must be inside repo root or /tmp
    try:
        p.relative_to(root)
        return p
    except ValueError:
        pass
    if p.is_relative_to(Path("/tmp")):
        return p
    return None


def _cap(s: str) -> tuple[str, bool]:
    """Cap output at _OUTPUT_CAP chars. Returns (text, truncated)."""
    if len(s) <= _OUTPUT_CAP:
        return s, False
    return s[:_OUTPUT_CAP] + "\n... (output truncated)", True


# ── RunCodeTool ──────────────────────────────────────────────────────────────


class RunCodeTool(Tool):
    """Execute a Python code snippet using the project virtual environment.

    The code runs in a subprocess using `.venv/bin/python`, not system Python.
    stdin is closed; stdout and stderr are captured. No network access is
    added beyond what the venv already has. Use this to verify logic, run
    diagnostics, or test snippets before committing them to a file.

    NOTE: The code runs with whatever packages are installed in .venv.
    For structural tests of the sovereign_agent package, prefer run_tests().
    """

    name = "run_code"
    tier = 1
    description = (
        "Execute a Python code snippet in the project venv (.venv/bin/python). "
        "Args: code (string), timeout (default 30s, up to 600s for a "
        "legitimately slow run — ask for more time explicitly rather than "
        "letting it time out). "
        "Captures stdout + stderr + exit_code. Never uses system Python. "
        "FAILURE MODES: venv_not_found, timeout, syntax_error, runtime_error, output_truncated."
    )
    failure_modes = (
        "venv_not_found",
        "timeout",
        "syntax_error",
        "runtime_error",
        "output_truncated",
    )

    class Args(BaseModel):
        code: str = Field(description="Python code to execute.")
        # timeout-hardening-d (Kevin, 2026-07-21): "adaptable timeouts...
        # and longer timeouts" — the old ceiling (120s) was too tight for
        # legitimately slow snippets (data processing, model calls). Raised
        # to 600s; the default (30s) is unchanged, so nothing gets slower
        # by default — only a deliberate ask for more time gets it.
        timeout: int = Field(default=_TIMEOUT_DEFAULT, ge=1, le=600, description="Timeout in seconds.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        python = _find_venv_python(root)
        if python is None:
            return ToolResult(
                ok=False,
                error=(
                    f"venv not found in {root}. "
                    "Expected .venv/bin/python. Cannot run code without the venv."
                ),
            )

        try:
            result = subprocess.run(
                [str(python), "-c", args.code],
                capture_output=True,
                text=True,
                timeout=args.timeout,
                stdin=subprocess.DEVNULL,
                cwd=root,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error=f"execution timed out after {args.timeout}s")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"subprocess error: {exc!r}")

        combined = (result.stdout or "") + (result.stderr or "")
        output, truncated = _cap(combined)

        return ToolResult(
            ok=result.returncode == 0,
            output=output,
            error=None if result.returncode == 0 else f"exit code {result.returncode}",
            metadata={
                "exit_code": result.returncode,
                "stdout_len": len(result.stdout or ""),
                "stderr_len": len(result.stderr or ""),
                "truncated": truncated,
                "python": str(python),
            },
        )


# ── RunShellTool ─────────────────────────────────────────────────────────────


class RunShellTool(Tool):
    """Execute a whitelisted shell command in the project directory.

    Only commands in the hardcoded allowlist are permitted:
      pytest, ruff, mypy, python, python3,
      ls, find, grep, wc, head, tail, cat, diff, stat, tree, echo

    No shell metacharacters (|, ;, &, <, >, `, $, \\) are permitted in args.
    The cwd must be inside the repo root or /tmp.

    For running Python code snippets, use run_code() instead.
    For running tests specifically, use run_tests() for a cleaner interface.
    """

    name = "run_shell"
    tier = 1
    description = (
        "Execute a whitelisted shell command in the project directory. "
        f"Allowed commands: {', '.join(sorted(SHELL_ALLOWLIST))}. "
        "Args: command (from allowlist), args (list of strings, no shell metacharacters), "
        "cwd (optional, must be inside repo root or /tmp), timeout "
        "(default 30s, up to 1800s for a legitimately slow build/install — "
        "ask for more time explicitly rather than letting it time out). "
        "FAILURE MODES: command_not_allowed, metachar_in_args, cwd_scope_violation, "
        "timeout, command_not_found, runtime_error."
    )
    failure_modes = (
        "command_not_allowed",
        "metachar_in_args",
        "cwd_scope_violation",
        "command_not_found",
        "timeout",
        "runtime_error",
        "output_truncated",
    )

    class Args(BaseModel):
        command: str = Field(description=f"Command to run. Must be one of: {', '.join(sorted(SHELL_ALLOWLIST))}.")
        args: list[str] = Field(default_factory=list, description="Arguments for the command (no shell metacharacters).")
        cwd: Optional[str] = Field(default=None, description="Working directory (must be inside repo root or /tmp).")
        # timeout-hardening-d (Kevin, 2026-07-21): ceiling raised 300s->1800s
        # (30 min) for legitimately slow builds/installs; default (30s)
        # unchanged.
        timeout: int = Field(default=_TIMEOUT_DEFAULT, ge=1, le=1800)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        # Validate command
        if args.command not in SHELL_ALLOWLIST:
            # tool-shell-confusion-d (found live 2026-08-03): a model tried
            # `run_shell(command="godot_check")` three times in a row,
            # then guessed at nonexistent wrapper scripts (sh/bash
            # godot_check.sh) — it had godot_check as a real, directly
            # callable tool the whole time. Name the collision explicitly
            # so this doesn't burn the same retries again.
            from ..authority import _TIER_REGISTRY
            hint = (
                f" {args.command!r} is a registered tool, not a shell "
                f"command — call it directly instead of via run_shell."
                if args.command in _TIER_REGISTRY else ""
            )
            return ToolResult(
                ok=False,
                error=(
                    f"command {args.command!r} is not in the allowlist.{hint} "
                    f"Allowed: {', '.join(sorted(SHELL_ALLOWLIST))}"
                ),
            )

        # Validate args for shell metacharacters
        for a in args.args:
            if _METACHAR.search(a):
                return ToolResult(
                    ok=False,
                    error=f"shell metacharacter found in argument {a!r} — not permitted",
                )

        root = _repo_root()
        validated_cwd = _validate_cwd(args.cwd, root)
        if validated_cwd is None:
            return ToolResult(
                ok=False,
                error=(
                    f"cwd {args.cwd!r} is outside the repo root ({root}) and /tmp. "
                    "Only paths inside the repo root or /tmp are permitted."
                ),
            )

        # Resolve the command: prefer venv version for python/pytest/ruff/mypy
        if args.command in ("pytest", "ruff", "mypy"):
            venv_cmd = _find_venv_cmd(root, args.command)
            cmd_path = str(venv_cmd) if venv_cmd else args.command
        elif args.command in ("python", "python3"):
            venv_py = _find_venv_python(root)
            cmd_path = str(venv_py) if venv_py else args.command
        else:
            cmd_path = args.command

        try:
            result = subprocess.run(
                [cmd_path, *args.args],
                capture_output=True,
                text=True,
                timeout=args.timeout,
                stdin=subprocess.DEVNULL,
                cwd=validated_cwd,
            )
        except FileNotFoundError:
            return ToolResult(ok=False, error=f"command not found: {cmd_path!r}")
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error=f"command timed out after {args.timeout}s")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"subprocess error: {exc!r}")

        combined = (result.stdout or "") + (result.stderr or "")
        output, truncated = _cap(combined)

        return ToolResult(
            ok=result.returncode == 0,
            output=output,
            error=None if result.returncode == 0 else f"exit code {result.returncode}",
            metadata={
                "command": args.command,
                "exit_code": result.returncode,
                "truncated": truncated,
                "cwd": str(validated_cwd),
            },
        )


# ── RunTestsTool ─────────────────────────────────────────────────────────────


class RunTestsTool(Tool):
    """Run pytest in the project virtual environment.

    A convenience wrapper around run_shell("pytest"). Returns the full pytest
    output including pass/fail counts, test names, and tracebacks on failure.
    Use `path` to run a specific test file or directory. Use `pattern` to
    filter by test name (equivalent to pytest -k).

    This is the primary way to verify code correctness after writing or
    modifying files. Call it after every non-trivial code change.
    """

    name = "run_tests"
    tier = 1
    description = (
        "Run pytest in the project venv. "
        "Args: path (default 'tests/'), pattern (optional -k filter), "
        "timeout (default 120s, up to 1800s for a genuinely large suite). "
        "Returns: full pytest output with pass/fail counts. "
        "Call after writing or modifying code to verify correctness. "
        "FAILURE MODES: venv_not_found, tests_not_found, timeout, test_failures, output_truncated."
    )
    failure_modes = (
        "venv_not_found",
        "tests_not_found",
        "timeout",
        "test_failures",
        "output_truncated",
    )

    class Args(BaseModel):
        path: str = Field(default="tests/", description="Test path or file to run.")
        pattern: str = Field(default="", description="Filter tests by name (pytest -k pattern).")
        # timeout-hardening-d (Kevin, 2026-07-21): ceiling raised 600s->1800s;
        # default (120s) unchanged.
        timeout: int = Field(default=120, ge=10, le=1800)

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        root = _repo_root()
        pytest_cmd = _find_venv_cmd(root, "pytest")
        if pytest_cmd is None:
            # Try system pytest as fallback
            pytest_cmd = Path("pytest")

        cmd_args = [str(pytest_cmd), args.path, "-v", "--tb=short", "--no-header"]
        if args.pattern:
            cmd_args += ["-k", args.pattern]

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                stdin=subprocess.DEVNULL,
                cwd=root,
            )
        except FileNotFoundError:
            return ToolResult(ok=False, error="pytest not found — install it in the venv first")
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error=f"pytest timed out after {args.timeout}s")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"subprocess error: {exc!r}")

        combined = (result.stdout or "") + (result.stderr or "")
        output, truncated = _cap(combined)

        # Parse pass/fail summary from last few lines
        passed = failed = errors = 0
        for ln in combined.splitlines()[-10:]:
            import re
            m = re.search(r"(\d+) passed", ln)
            if m:
                passed = int(m.group(1))
            m = re.search(r"(\d+) failed", ln)
            if m:
                failed = int(m.group(1))
            m = re.search(r"(\d+) error", ln)
            if m:
                errors = int(m.group(1))

        ok = result.returncode == 0
        return ToolResult(
            ok=ok,
            output=output,
            error=None if ok else f"pytest exited {result.returncode}: {failed} failed, {errors} errors",
            metadata={
                "exit_code": result.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "truncated": truncated,
                "path": args.path,
            },
        )
