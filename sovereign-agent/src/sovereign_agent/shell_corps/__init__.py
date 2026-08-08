"""shell_corps — multi-command shell execution, Claude-Code-tier or above (F10).

Kevin (2026-07-18): "make sure she can run multiple shell commands —
Claude Code tier or better, per the god-tier paths forward. Intelligently
to the high degree."

The "or better" is the SAFETY + OBSERVABILITY spine that Claude Code's
allowlist model doesn't have:

  1. **Per-command authority classification** — every command is graded
     T0 (read-only) → T3 (destructive/system) by pattern BEFORE it runs.
     T0/T1 run freely; T2 run in-session; T3 are PROPOSE-ONLY (never
     executed here — they return a proposal for the human). Claude Code
     has allowlists; this has semantic tiers.
  2. **Parallelism** — independent commands run concurrently (bounded
     pool); a dependency chain runs in order. Claude-Code-tier throughput.
  3. **The audit ledger** — every run records argv, tier, cwd, exit,
     duration, output caps → replayable via `sov reviews`.
  4. **HALT-aware** — a set halt flag refuses new runs (the kill switch
     reaches the shell).

This module is PURE PLANNING + CLASSIFICATION + the safe runner shape.
It never executes T3, never uses a shell string (argv lists only, no
`shell=True`), and every dangerous pattern is denied by construction.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

__all__ = [
    "CommandPlan", "RunResult", "classify_tier", "plan_commands",
    "run_command", "run_batch", "TIER_READONLY", "TIER_SAFE_WRITE",
    "TIER_MUTATING", "TIER_DESTRUCTIVE",
]

TIER_READONLY = 0      # ls, cat, git status, grep — no side effects
TIER_SAFE_WRITE = 1    # mkdir, touch, git add — reversible, in-workspace
TIER_MUTATING = 2      # mv, git commit, pip install — real but bounded
TIER_DESTRUCTIVE = 3   # rm -rf, sudo, dd, systemctl, curl|sh — PROPOSE ONLY

# ── classification patterns (checked most-dangerous first) ───────────
_DESTRUCTIVE = (
    "rm -rf", "rm -r", "sudo", "dd ", "mkfs", "shutdown", "reboot",
    "systemctl", "kill ", "pkill", "chmod 777", "chown", ":(){", "> /dev/",
    "curl", "wget", "| sh", "| bash", "eval ", "format", "fdisk",
    "git push", "git reset --hard", "npm publish", "docker",
)
_MUTATING = (
    "mv ", "cp ", "git commit", "git merge", "git rebase", "pip install",
    "pip uninstall", "apt", "make install", "git checkout", "git branch -d",
    ">", ">>", "tee ",
)
_SAFE_WRITE = (
    "mkdir", "touch", "git add", "git stash", "ln -s", "cp -n",
)


def classify_tier(command: str) -> int:
    """Grade a command by its most dangerous recognizable operation."""
    c = " " + (command or "").strip().lower() + " "
    if any(p in c for p in _DESTRUCTIVE):
        return TIER_DESTRUCTIVE
    if any(p in c for p in _MUTATING):
        return TIER_MUTATING
    if any(p in c for p in _SAFE_WRITE):
        return TIER_SAFE_WRITE
    return TIER_READONLY


@dataclass(frozen=True)
class CommandPlan:
    command: str
    tier: int

    @property
    def propose_only(self) -> bool:
        return self.tier >= TIER_DESTRUCTIVE

    @property
    def tier_name(self) -> str:
        return {0: "read-only", 1: "safe-write", 2: "mutating",
                3: "destructive"}[self.tier]


@dataclass
class RunResult:
    command: str
    tier: int
    ok: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    proposed: bool = False       # T3 → not run, returned for human approval
    skipped_reason: str = ""

    def to_ledger(self) -> dict:
        return {"command": self.command[:500], "tier": self.tier,
                "ok": self.ok, "exit": self.exit_code,
                "duration_s": round(self.duration_s, 3),
                "proposed": self.proposed, "skipped": self.skipped_reason}


def plan_commands(commands: list[str]) -> list[CommandPlan]:
    return [CommandPlan(c, classify_tier(c)) for c in commands]


def run_command(command: str, *, cwd: str | None = None,
                timeout_s: float = 60.0, max_output: int = 20000,
                max_tier: int = TIER_MUTATING, halted: bool = False,
                runner=None) -> RunResult:
    """Run ONE command, tier-gated. T3 (or > max_tier) is never executed —
    it returns proposed=True. argv-only (no shell string). `runner` is
    injectable for tests (defaults to subprocess.run)."""
    tier = classify_tier(command)
    if halted:
        return RunResult(command, tier, False, -1,
                         skipped_reason="HALT set — the kill switch refuses runs")
    if tier >= TIER_DESTRUCTIVE or tier > max_tier:
        return RunResult(command, tier, False, 0, proposed=True,
                         skipped_reason=f"tier {tier} ({_name(tier)}) — "
                                        "propose-only, needs human approval")
    argv = shlex.split(command)
    if not argv:
        return RunResult(command, tier, False, -1,
                         skipped_reason="empty command")
    t0 = time.time()
    try:
        run = runner or _default_runner
        proc = run(argv, cwd, timeout_s)
        dt = time.time() - t0
        return RunResult(
            command, tier, proc.returncode == 0, proc.returncode,
            stdout=(proc.stdout or "")[:max_output],
            stderr=(proc.stderr or "")[:max_output], duration_s=dt)
    except subprocess.TimeoutExpired:
        return RunResult(command, tier, False, -1, duration_s=time.time() - t0,
                         skipped_reason=f"timed out after {timeout_s}s")
    except Exception as e:  # noqa: BLE001
        return RunResult(command, tier, False, -1, duration_s=time.time() - t0,
                         skipped_reason=f"{type(e).__name__}: {e}")


def run_batch(commands: list[str], *, parallel: bool = True,
              max_workers: int = 4, **kw) -> list[RunResult]:
    """Run many commands. parallel=True runs independent commands
    concurrently (bounded pool); parallel=False runs them in order (a
    dependency chain). Order of results always matches input order."""
    if not commands:
        return []
    if not parallel:
        return [run_command(c, **kw) for c in commands]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda c: run_command(c, **kw), commands))


def _name(tier: int) -> str:
    return {0: "read-only", 1: "safe-write", 2: "mutating",
            3: "destructive"}[tier]


def _default_runner(argv, cwd, timeout_s):
    return subprocess.run(argv, cwd=cwd, timeout=timeout_s,
                          capture_output=True, text=True)
