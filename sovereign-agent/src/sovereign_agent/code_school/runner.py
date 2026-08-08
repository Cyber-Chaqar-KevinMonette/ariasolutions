"""runner — grade a drill by actually running the submitted code.

This is the only part of the school that executes text a human typed, so it
gets the tightest box in the system:

  • **bwrap**, via the existing `sandbox.build_bwrap_argv` — `--unshare-net`
    (no network at all), `--unshare-pid`, and the project directory bound
    READ-ONLY. Mode.BUSY is passed deliberately: it is the mode whose whole
    purpose is a read-only project bind.
  • **A wall-clock timeout**, killed the hard way. An infinite loop is the
    single likeliest thing a learner submits, and it must cost seconds.
  • **Output truncated** before it ever reaches Discord.
  • **Refuses to run at all if bwrap is missing** rather than falling back
    to bare `exec`. A grader that silently downgrades its own isolation is
    worse than one that says no — the whole value here is that "it ran
    safely" means something.

Grading is pass/fail on the drill's asserts, and a failure returns the
assertion message, because "wrong" without "why" teaches nothing.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DrillResult", "run_drill", "TIMEOUT_S", "MAX_OUTPUT"]

TIMEOUT_S = 10.0
MAX_OUTPUT = 1500
MAX_SOURCE = 20_000        # a drill answer is never 20k of code


@dataclass(frozen=True)
class DrillResult:
    passed: bool
    detail: str
    timed_out: bool = False
    blocked: bool = False      # refused before running (bad input / no sandbox)

    @property
    def icon(self) -> str:
        return "✅" if self.passed else ("⏱" if self.timed_out else "❌")


def _harness(submission: str, tests: str) -> str:
    """The learner's code, then the drill's asserts.

    The asserts run in the same module namespace, so they see whatever the
    submission defined. AssertionError is caught and reported as the failure
    reason; anything else is reported with its type so a NameError reads
    differently from a wrong answer.
    """
    return (
        "import sys\n"
        "# ── submission ──\n"
        f"{submission}\n\n"
        "# ── checks ──\n"
        "try:\n"
        "    " + "\n    ".join((tests or "pass").strip().splitlines()) + "\n"
        "except AssertionError as exc:\n"
        "    print('FAIL: ' + (str(exc) or 'an assertion failed'))\n"
        "    sys.exit(1)\n"
        "except Exception as exc:\n"
        "    print('ERROR: ' + type(exc).__name__ + ': ' + str(exc))\n"
        "    sys.exit(2)\n"
        "print('PASS')\n"
    )


def run_drill(submission: str, tests: str, *,
              python_bin: str = "python3",
              timeout_s: float = TIMEOUT_S,
              runner=None) -> DrillResult:
    """Execute `submission` against `tests` inside bwrap. Never raises.

    `runner` is injectable so the grading logic is testable without actually
    spawning a sandbox.
    """
    submission = (submission or "").strip()
    if not submission:
        return DrillResult(False, "No code submitted.", blocked=True)
    if len(submission) > MAX_SOURCE:
        return DrillResult(False, "Submission too large.", blocked=True)

    from sovereign_agent.modes import Mode
    from sovereign_agent.sandbox import bwrap_available, build_bwrap_argv

    if runner is None and not bwrap_available():
        # Deliberately no fallback: running someone's code without isolation
        # because the sandbox is missing would defeat the point entirely.
        return DrillResult(
            False,
            "Sandbox (bwrap) unavailable — refusing to run code unisolated.",
            blocked=True)

    with tempfile.TemporaryDirectory(prefix="drill-") as tmp:
        script = Path(tmp) / "drill.py"
        script.write_text(_harness(submission, tests), encoding="utf-8")
        inner = [python_bin, "-I", "-S", str(script)]

        if runner is None:
            argv = build_bwrap_argv(
                mode=Mode.BUSY,            # BUSY == project dir bound READ-ONLY
                project_dir=Path(tmp),
                inner_argv=inner,
                network=False,             # --unshare-net
            )
        else:
            argv = inner

        try:
            if runner is not None:
                rc, out = runner(argv)
            else:
                proc = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=timeout_s)
                rc = proc.returncode
                out = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            return DrillResult(
                False,
                f"Timed out after {timeout_s:.0f}s — is there an infinite loop?",
                timed_out=True)
        except Exception as exc:  # noqa: BLE001 — a grader must never crash the bot
            return DrillResult(False, f"Could not run: {type(exc).__name__}",
                               blocked=True)

    text = (out or "").strip()
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + "\n…(truncated)"
    if rc == 0 and "PASS" in text:
        return DrillResult(True, "All checks passed.")
    return DrillResult(False, text or f"Exited {rc} with no output.")
