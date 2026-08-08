"""
╔══════════════════════════════════════════════════════════════════════════╗
║  workflow/handlers/shell.py — shell tool handler                          ║
║  v0.2.38 muscle drop                                                       ║
║                                                                           ║
║  Lets the agentic loop execute shell commands as workflow steps. With   ║
║  a whitelist, a timeout, captured stdout+stderr, and no shell=True      ║
║  unless explicitly enabled.                                              ║
║                                                                           ║
║  Discipline                                                              ║
║                                                                           ║
║    • Default whitelist mode — only commands whose first token is in     ║
║      the allowlist may run. Tightens the blast radius from "any         ║
║      arbitrary command Aria's planner decides on" to "the small set    ║
║      Kevin explicitly enabled."                                          ║
║                                                                           ║
║    • Per-call timeout — no command runs forever. Default 30s.          ║
║                                                                           ║
║    • cwd defaults to the project's repo_path if available, else cwd.   ║
║                                                                           ║
║    • Output captured to outcome.extra['stdout'] / 'stderr']            ║
║      (truncated to keep DB rows reasonable).                            ║
║                                                                           ║
║    • shell=False by default. The PlanStep can opt-in to shell=True for ║
║      operations that need pipes/redirects — at which point the         ║
║      command goes through Bash and the canon clause kicks in:          ║
║      shell=True commands MUST come from a pre-approved playbook,       ║
║      not from arbitrary planner output. (Enforced by the playbook      ║
║      gate in v0.2.39; for now, shell=True is loud in the outcome.)    ║
║                                                                           ║
║  Action input shape                                                     ║
║                                                                           ║
║    {                                                                     ║
║      "argv": ["uv", "run", "python", "-V"],     # required           ║
║      "cwd": "/home/kmon/AA-Erebo/sovereign-agent",  # optional       ║
║      "timeout_sec": 30,                          # optional, default 30 ║
║      "use_shell": false,                         # optional, default off║
║      "env": {"FOO": "bar"}                       # optional, merged in ║
║    }                                                                     ║
║                                                                           ║
║  Kill switch: SOV_NO_SHELL_HANDLER=1                                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from sovereign_agent.persistence.projects import Task
from sovereign_agent.workflow.agentic_loop import StepOutcome


KILL_SWITCH_ENV = "SOV_NO_SHELL_HANDLER"

# Sensible default whitelist. Extend per project via ShellHandler(allowlist=[...]).
# The intent: read-only or project-build operations only. Mutation (rm, mv,
# system-level installs) is NOT here by default — add explicitly per project.
DEFAULT_ALLOWLIST = frozenset({
    "uv", "python", "python3", "pip",
    "git", "ls", "cat", "echo", "pwd",
    "head", "tail", "wc", "grep",
    "make", "ruff", "mypy", "pytest",
})

_STDOUT_CAP = 16_384   # 16 KB cap on captured streams
_STDERR_CAP = 16_384


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ShellHandler:
    """A workflow tool handler that runs shell commands with discipline."""

    def __init__(
        self,
        allowlist: Optional[set[str]] = None,
        default_timeout_sec: int = 30,
        default_cwd: Optional[str] = None,
    ):
        self._allowlist = frozenset(allowlist) if allowlist else DEFAULT_ALLOWLIST
        self._default_timeout = default_timeout_sec
        self._default_cwd = default_cwd

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_ENV))

    @property
    def allowlist(self) -> frozenset[str]:
        return self._allowlist

    def __call__(self, task: Task) -> StepOutcome:
        """The handler signature the AgenticLoop expects."""
        started_at = _iso_now()

        if self.is_disabled:
            return StepOutcome(
                succeeded=False,
                summary="shell handler disabled via SOV_NO_SHELL_HANDLER",
                error="handler-disabled",
                started_at=started_at,
                completed_at=_iso_now(),
            )

        # Parse the action input from the task's description blob.
        try:
            blob = json.loads(task.description)
            action_input = blob.get("action_input", {})
        except (json.JSONDecodeError, AttributeError):
            return StepOutcome(
                succeeded=False,
                summary="malformed task description; cannot parse action_input",
                error="malformed-description",
                started_at=started_at,
                completed_at=_iso_now(),
            )

        argv = action_input.get("argv")
        if not argv or not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
            return StepOutcome(
                succeeded=False,
                summary="action_input.argv must be a non-empty list of strings",
                error="invalid-argv",
                started_at=started_at,
                completed_at=_iso_now(),
            )

        use_shell = bool(action_input.get("use_shell", False))
        timeout = int(action_input.get("timeout_sec", self._default_timeout))
        cwd = action_input.get("cwd") or self._default_cwd or os.getcwd()
        extra_env = action_input.get("env") or {}
        if not isinstance(extra_env, dict):
            extra_env = {}

        # Whitelist check.
        command_name = argv[0]
        if command_name not in self._allowlist:
            return StepOutcome(
                succeeded=False,
                summary=f"command {command_name!r} not in shell allowlist",
                error="allowlist-rejection",
                extra={
                    "allowlist": sorted(self._allowlist),
                    "attempted_command": command_name,
                },
                started_at=started_at,
                completed_at=_iso_now(),
            )

        # Build the environment.
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in extra_env.items()})

        # Execute.
        try:
            if use_shell:
                # Reconstruct a shell command from argv tokens.
                cmd_str = " ".join(shlex.quote(a) for a in argv)
                result = subprocess.run(
                    cmd_str, shell=True, cwd=cwd, env=env,
                    capture_output=True, text=True,
                    timeout=timeout,
                )
            else:
                result = subprocess.run(
                    argv, shell=False, cwd=cwd, env=env,
                    capture_output=True, text=True,
                    timeout=timeout,
                )
        except subprocess.TimeoutExpired:
            return StepOutcome(
                succeeded=False,
                summary=f"command timed out after {timeout}s",
                error="timeout",
                extra={"argv": argv, "timeout_sec": timeout},
                started_at=started_at,
                completed_at=_iso_now(),
            )
        except FileNotFoundError:
            return StepOutcome(
                succeeded=False,
                summary=f"command not found: {command_name}",
                error="command-not-found",
                extra={"argv": argv},
                started_at=started_at,
                completed_at=_iso_now(),
            )
        except Exception as e:
            return StepOutcome(
                succeeded=False,
                summary=f"shell execution raised {type(e).__name__}",
                error=str(e),
                extra={"argv": argv},
                started_at=started_at,
                completed_at=_iso_now(),
            )

        # Build outcome.
        stdout = (result.stdout or "")[:_STDOUT_CAP]
        stderr = (result.stderr or "")[:_STDERR_CAP]
        succeeded = result.returncode == 0
        return StepOutcome(
            succeeded=succeeded,
            summary=(
                f"{command_name} exited {result.returncode}"
                if succeeded
                else f"{command_name} failed with code {result.returncode}"
            ),
            error="" if succeeded else f"exit-code-{result.returncode}",
            extra={
                "argv": argv,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "cwd": cwd,
                "used_shell": use_shell,
            },
            started_at=started_at,
            completed_at=_iso_now(),
        )


__all__ = ["ShellHandler", "DEFAULT_ALLOWLIST", "KILL_SWITCH_ENV"]
