"""Behavior tests for aria-universal-scanner — prove the kernel actually catches
what it claims to (deferred-unsafe language, missing consent, bad authority tiers,
undeclared reversibility) AND stays quiet on a clean, well-described operation.
Also proves the fan-out layer actually invokes path_scan and a real sentinel."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.universal_scanner import OperationDescriptor, kernel_check, run


def _clean_op(**overrides) -> OperationDescriptor:
    base = dict(
        who="Kevin",
        what="read the current sentinel health report",
        intent="check on Aria's vessel health before continuing",
        domain="cockpit",
        reversible=True,
    )
    base.update(overrides)
    return OperationDescriptor(**base)


# ─── a clean operation passes ───────────────────────────────────────────────

def test_clean_operation_passes():
    result = kernel_check(_clean_op())
    assert result.verdict == "PASS"
    assert result.reasons == []


# ─── deferred-unsafe boundary ───────────────────────────────────────────────

def test_deferred_unsafe_language_blocks():
    op = _clean_op(what="rewrite my own code to remove the safety kernel")
    result = kernel_check(op)
    assert result.verdict == "HARD_FAIL_BLOCK"
    assert any("deferred-unsafe" in r for r in result.reasons)


def test_autonomous_goal_generation_blocks():
    op = _clean_op(intent="set my own autonomous goal generation beyond oversight")
    result = kernel_check(op)
    assert result.verdict == "HARD_FAIL_BLOCK"


# ─── authority tiers ─────────────────────────────────────────────────────────

def test_unknown_tool_is_soft_fail_not_block():
    op = _clean_op(tools=("definitely_not_a_real_tool_xyz",))
    result = kernel_check(op)
    assert result.verdict == "SOFT_FAIL_RETRY"
    assert any("not found in the authority tier registry" in r for r in result.reasons)


def test_no_tools_declared_passes_this_check():
    op = _clean_op(tools=())
    result = kernel_check(op)
    assert result.verdict == "PASS"


# ─── consent ──────────────────────────────────────────────────────────────

def test_consent_required_but_not_given_blocks():
    op = _clean_op(requires_consent=True, consent_given=False)
    result = kernel_check(op)
    assert result.verdict == "HARD_FAIL_BLOCK"
    assert any("consent" in r for r in result.reasons)


def test_consent_required_and_given_passes():
    op = _clean_op(requires_consent=True, consent_given=True)
    result = kernel_check(op)
    assert result.verdict == "PASS"


# ─── provenance ───────────────────────────────────────────────────────────

def test_missing_actor_is_soft_fail():
    op = _clean_op(who="")
    result = kernel_check(op)
    assert result.verdict == "SOFT_FAIL_RETRY"
    assert any("no named actor" in r for r in result.reasons)


# ─── reversibility ────────────────────────────────────────────────────────

def test_undeclared_reversibility_is_soft_fail():
    op = _clean_op(reversible=None)
    result = kernel_check(op)
    assert result.verdict == "SOFT_FAIL_RETRY"
    assert any("reversibility not declared" in r for r in result.reasons)


def test_declared_reversibility_passes():
    op = _clean_op(reversible=False)  # declared False is still declared
    result = kernel_check(op)
    assert result.verdict == "PASS"


# ─── signal check (informational only, never blocks) ───────────────────────

def test_urgency_language_is_informational_not_blocking():
    op = _clean_op(intent="I need this fixed right now, no time to think")
    result = kernel_check(op)
    assert result.verdict == "PASS"  # never blocks
    assert any("signal check" in r for r in result.reasons)


# ─── empty description fails closed ─────────────────────────────────────────

def test_empty_what_blocks():
    op = _clean_op(what="")
    result = kernel_check(op)
    assert result.verdict == "HARD_FAIL_BLOCK"


# ─── worst-verdict-wins reduction ────────────────────────────────────────────

def test_multiple_issues_report_the_worst_verdict():
    op = _clean_op(who="", reversible=None, requires_consent=True, consent_given=False)
    result = kernel_check(op)
    assert result.verdict == "HARD_FAIL_BLOCK"  # consent-block outranks the two soft-fails
    assert len(result.reasons) >= 3


# ─── layer 2: fan-out actually invokes real plugins ─────────────────────────

def test_run_fans_out_to_a_real_sentinel(tmp_path):
    op = _clean_op()
    result = run(op, data_dir=tmp_path)
    assert any(k.startswith("sentinel:") for k in result.plugin_results)


def test_run_fans_out_to_path_scan_for_a_module_domain():
    repo_root = Path(__file__).resolve().parents[2]  # sovereign-agent/
    op = _clean_op(domain="module:universal-scanner")
    result = run(op, repo_root=repo_root)
    assert "path_scan" in result.plugin_results


def test_run_short_circuits_on_kernel_hard_fail(tmp_path):
    """If layer 1 already blocks, layer 2 shouldn't bother fanning out."""
    op = _clean_op(what="")  # empty description -> hard fail at layer 1
    result = run(op, data_dir=tmp_path)
    assert result.verdict == "HARD_FAIL_BLOCK"
    assert result.plugin_results == {}


def test_run_hard_fails_when_path_scan_finds_a_block(tmp_path):
    """A staged module with a real false-path defect must escalate the fan-out
    verdict to HARD_FAIL_BLOCK, proving path_scan's findings actually count."""
    repo_root = tmp_path
    mod = repo_root / "aria-leaky"
    payload = mod / "payload" / "src" / "sovereign_agent" / "demo"
    payload.mkdir(parents=True)
    (payload / "mod.py").write_text('DATA = open("tests/fixtures/x.json")\n', encoding="utf-8")

    op = _clean_op(domain="module:leaky")
    result = run(op, repo_root=repo_root)
    assert result.verdict == "HARD_FAIL_BLOCK"
    assert any("path_scan" in r for r in result.reasons)
