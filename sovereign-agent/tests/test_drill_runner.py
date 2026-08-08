"""Tests for code_school.runner — grading, and the isolation that makes
running submitted code acceptable at all.

The escape tests at the bottom actually spawn bwrap. They are the reason
this feature is safe to ship, so they run for real rather than against a
stub.
"""
from __future__ import annotations

import pytest

from sovereign_agent.code_school import drills as D
from sovereign_agent.code_school.runner import MAX_SOURCE, run_drill
from sovereign_agent.sandbox import bwrap_available

needs_bwrap = pytest.mark.skipif(not bwrap_available(),
                                 reason="bwrap not installed")


# ── input guards (no execution) ────────────────────────────────────────
def test_empty_submission_is_refused():
    r = run_drill("", "assert True")
    assert not r.passed and r.blocked


def test_oversized_submission_is_refused():
    r = run_drill("x = 1\n" * MAX_SOURCE, "assert True")
    assert not r.passed and r.blocked


# ── grading logic, injected runner (no subprocess) ─────────────────────
def test_pass_is_detected():
    r = run_drill("def f(): pass", "assert True",
                  runner=lambda argv: (0, "PASS"))
    assert r.passed and r.icon == "✅"


def test_failure_reports_the_assertion_message():
    r = run_drill("def f(): pass", "assert False, 'nope'",
                  runner=lambda argv: (1, "FAIL: nope"))
    assert not r.passed and "nope" in r.detail


def test_runner_never_raises_on_a_broken_launcher():
    def boom(argv):
        raise OSError("no exec for you")
    r = run_drill("x = 1", "assert True", runner=boom)
    assert not r.passed and r.blocked, "a grader must never crash the bot"


def test_huge_output_is_truncated():
    r = run_drill("x = 1", "assert True",
                  runner=lambda argv: (1, "E" * 50_000))
    assert len(r.detail) < 2_000 and "truncated" in r.detail


# ── real execution ─────────────────────────────────────────────────────
@needs_bwrap
def test_a_correct_answer_really_passes():
    d = D.by_id("fix-the-swallow")
    good = (
        "def safe_call(fn, log):\n"
        "    try:\n"
        "        return fn()\n"
        "    except Exception as exc:\n"
        "        log.append(str(exc))\n"
        "        return None\n"
    )
    r = run_drill(good, d.tests)
    assert r.passed, r.detail


@needs_bwrap
def test_the_swallow_bug_itself_fails_the_drill():
    """The whole lesson: silently discarding the error must NOT pass."""
    swallowing = (
        "def safe_call(fn, log):\n"
        "    try:\n"
        "        return fn()\n"
        "    except Exception:\n"
        "        return None\n"          # the bug — nothing recorded
    )
    r = run_drill(swallowing, D.by_id("fix-the-swallow").tests)
    assert not r.passed
    assert "recorded" in r.detail or "FAIL" in r.detail


@needs_bwrap
def test_a_name_error_reads_differently_from_a_wrong_answer():
    r = run_drill("# nothing defined\n", D.by_id("monotone-curve").tests)
    assert not r.passed and "ERROR" in r.detail


# ── isolation ──────────────────────────────────────────────────────────
@needs_bwrap
def test_network_access_is_impossible():
    """--unshare-net. A drill answer must not be able to phone home."""
    r = run_drill(
        "import socket\n"
        "socket.create_connection(('1.1.1.1', 53), timeout=3)\n",
        "assert True")
    assert not r.passed, "network reached from inside the sandbox"


@needs_bwrap
def test_a_write_outside_the_sandbox_does_not_persist():
    """The property that matters is NOT that the write raises — bwrap gives
    the process a private root, so writing to an unbound path 'succeeds'
    inside the namespace and is discarded on exit. What must hold is that
    the REAL filesystem is untouched. (First version of this test asserted
    the wrong thing and reported a breach that hadn't happened.)"""
    import pathlib
    target = pathlib.Path("/home/kmon/drill-escape.txt")
    assert not target.exists(), "stale artifact from an earlier run"
    run_drill(f"open({str(target)!r}, 'w').write('pwned')\n", "assert True")
    assert not target.exists(), "submitted code persisted a file to real $HOME"


@needs_bwrap
def test_private_keys_are_masked_not_readable():
    """~/.ssh and friends are --ro-bind-try'd to /dev/null, so a drill that
    goes looking for credentials finds an empty file, not a key."""
    r = run_drill(
        "import pathlib\n"
        "p = pathlib.Path('/home/kmon/.ssh')\n"
        "leaked = p.is_dir() and any(p.iterdir())\n",
        "assert leaked is False, 'ssh key material was reachable'")
    assert r.passed, r.detail


@needs_bwrap
def test_an_infinite_loop_is_killed():
    r = run_drill("while True:\n    pass\n", "assert True", timeout_s=3.0)
    assert not r.passed and r.timed_out


@needs_bwrap
def test_the_repo_cannot_be_modified():
    """Mode.BUSY binds the project dir read-only — a drill must never be
    able to edit the codebase it is teaching from."""
    r = run_drill(
        "open('/home/kmon/AA-Erebo/sovereign-agent/pyproject.toml', 'a')"
        ".write('# tampered\\n')\n",
        "assert True")
    assert not r.passed, "submitted code modified the repository"
