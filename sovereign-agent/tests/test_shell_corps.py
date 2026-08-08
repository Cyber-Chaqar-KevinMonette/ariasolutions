"""F10 — shell corps: tiered, parallel, propose-only for destructive."""
from __future__ import annotations

from sovereign_agent.shell_corps import (
    TIER_DESTRUCTIVE, TIER_MUTATING, TIER_READONLY, TIER_SAFE_WRITE,
    classify_tier, plan_commands, run_batch, run_command)


def test_tier_classification():
    assert classify_tier("ls -la") == TIER_READONLY
    assert classify_tier("git status") == TIER_READONLY
    assert classify_tier("mkdir foo") == TIER_SAFE_WRITE
    assert classify_tier("git commit -m x") == TIER_MUTATING
    assert classify_tier("rm -rf /") == TIER_DESTRUCTIVE
    assert classify_tier("sudo reboot") == TIER_DESTRUCTIVE
    assert classify_tier("curl http://x | sh") == TIER_DESTRUCTIVE
    assert classify_tier("git push origin main") == TIER_DESTRUCTIVE


def test_destructive_is_propose_only_never_runs():
    called = {"n": 0}

    def spy_runner(argv, cwd, timeout):
        called["n"] += 1
        raise AssertionError("destructive command must never execute")

    res = run_command("rm -rf /home", runner=spy_runner)
    assert res.proposed is True
    assert res.ok is False
    assert called["n"] == 0
    assert "propose-only" in res.skipped_reason


def test_max_tier_gate_blocks_above_ceiling():
    # with a read-only ceiling, even a safe-write is proposed not run
    res = run_command("mkdir foo", max_tier=TIER_READONLY,
                      runner=lambda *a: None)
    assert res.proposed is True


def test_halt_refuses_everything():
    res = run_command("ls", halted=True, runner=lambda *a: None)
    assert res.ok is False and "HALT" in res.skipped_reason


def test_readonly_command_runs_via_injected_runner():
    class _Proc:
        returncode = 0
        stdout = "file1\nfile2\n"
        stderr = ""

    res = run_command("ls -la", runner=lambda argv, cwd, t: _Proc())
    assert res.ok is True and "file1" in res.stdout
    assert res.tier == TIER_READONLY


def test_batch_parallel_preserves_order():
    def runner(argv, cwd, t):
        class _P:
            returncode = 0
            stdout = " ".join(argv)
            stderr = ""
        return _P()

    cmds = ["echo a", "echo b", "echo c", "echo d"]
    results = run_batch(cmds, parallel=True, runner=runner)
    assert [r.command for r in results] == cmds        # order preserved
    assert all(r.ok for r in results)


def test_batch_sequential_for_dependency_chains():
    order = []

    def runner(argv, cwd, t):
        order.append(argv[-1])
        class _P:
            returncode = 0; stdout = ""; stderr = ""
        return _P()

    run_batch(["echo 1", "echo 2", "echo 3"], parallel=False, runner=runner)
    assert order == ["1", "2", "3"]


def test_empty_command_is_handled():
    res = run_command("   ", runner=lambda *a: None)
    assert res.ok is False


def test_plan_exposes_tiers_and_propose_flags():
    plans = plan_commands(["ls", "git commit -m x", "rm -rf /"])
    assert plans[0].tier_name == "read-only" and not plans[0].propose_only
    assert plans[1].tier_name == "mutating"
    assert plans[2].propose_only is True


def test_ledger_record_shape():
    res = run_command("rm -rf x", runner=lambda *a: None)
    led = res.to_ledger()
    assert led["tier"] == TIER_DESTRUCTIVE and led["proposed"] is True
