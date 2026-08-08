"""Behavior tests for unverified_claims.py — grounded-truth claim checking."""
from sovereign_agent.unverified_claims import (
    claims_verification,
    subtask_verified_by_trace,
    find_unverified_claims,
    render_unverified_claims_section,
)


def test_claims_verification_detects_common_phrasing():
    assert claims_verification("Fixed the bug, tests pass now.")
    assert claims_verification("All green, ready to ship.")
    assert claims_verification("Verified the endpoint returns 200.")
    assert claims_verification("Confirmed working after the patch.")


def test_claims_verification_false_on_plain_summary():
    assert not claims_verification("Wrote the README section.")
    assert not claims_verification("")
    assert not claims_verification(None)


def test_subtask_verified_by_trace_true_when_test_tool_ran():
    actions = [
        {"trace_id": "t1", "flag": "tool-start-d", "payload": {"tool": "run_pytest"}},
    ]
    assert subtask_verified_by_trace("t1", actions)


def test_subtask_verified_by_trace_false_when_no_matching_action():
    actions = [
        {"trace_id": "t1", "flag": "tool-start-d", "payload": {"tool": "write_file"}},
    ]
    assert not subtask_verified_by_trace("t1", actions)
    assert not subtask_verified_by_trace("", actions)
    assert not subtask_verified_by_trace("t2", actions)


def test_find_unverified_claims_flags_claim_without_proof():
    subtasks = [
        {"id": "s1", "description": "Fix parser bug", "trace_id": "t1",
         "result_summary": "Fixed the parser, all tests pass."},
    ]
    actions = [
        {"trace_id": "t1", "flag": "file-write-d", "payload": {"path": "parser.py"}},
    ]
    findings = find_unverified_claims(subtasks, actions)
    assert len(findings) == 1
    assert findings[0]["subtask_id"] == "s1"
    assert "parser" in findings[0]["claim"].lower()


def test_find_unverified_claims_clears_when_proof_present():
    subtasks = [
        {"id": "s1", "description": "Fix parser bug", "trace_id": "t1",
         "result_summary": "Fixed the parser, all tests pass."},
    ]
    actions = [
        {"trace_id": "t1", "flag": "tool-start-d", "payload": {"tool": "run_pytest"}},
    ]
    assert find_unverified_claims(subtasks, actions) == []


def test_find_unverified_claims_ignores_subtasks_with_no_claim():
    subtasks = [
        {"id": "s1", "description": "Write docs", "trace_id": "t1",
         "result_summary": "Wrote the docs section."},
    ]
    assert find_unverified_claims(subtasks, []) == []


def test_render_unverified_claims_section_clean_case():
    text = render_unverified_claims_section([], [])
    assert "## Unverified claims" in text
    assert "No claim/proof gaps detected" in text


def test_render_unverified_claims_section_flags_finding():
    subtasks = [
        {"id": "s1", "description": "Fix parser bug", "trace_id": "t1",
         "result_summary": "Verified the fix works correctly."},
    ]
    text = render_unverified_claims_section(subtasks, [])
    assert "1 subtask(s) claimed verification" in text
    assert "Fix parser bug" in text


def test_never_raises_on_malformed_input():
    assert find_unverified_claims(None, None) == []
    assert find_unverified_claims([{"result_summary": "tests pass"}], None) is not None
