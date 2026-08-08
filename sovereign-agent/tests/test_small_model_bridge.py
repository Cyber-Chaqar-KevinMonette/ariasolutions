"""Real behavior tests for aria-small-model-bridge — prove it rescues the
actual ways small (7B/8B) models mangle tool calls, and never invents one.
"""
from __future__ import annotations

from sovereign_agent.small_model_bridge import (
    bridge_report,
    coerce_args,
    extract_tool_calls_from_text,
    normalize_response,
)

KNOWN = {"aria_status", "read_session", "list_objectives"}


# ── coerce_args ──────────────────────────────────────────────────────────
def test_coerce_passes_through_a_real_dict():
    assert coerce_args({"a": 1}) == {"a": 1}


def test_coerce_parses_a_json_string():
    assert coerce_args('{"path": "x", "n": 2}') == {"path": "x", "n": 2}


def test_coerce_repairs_trailing_commas_and_single_quotes():
    assert coerce_args("{'path': 'x', 'n': 2,}") == {"path": "x", "n": 2}


def test_coerce_repairs_unquoted_keys():
    assert coerce_args('{path: "x"}') == {"path": "x"}


def test_coerce_empty_string_is_empty_dict():
    assert coerce_args("") == {}


def test_coerce_gives_up_cleanly_on_garbage():
    assert coerce_args("not json at all {[") is None
    assert coerce_args(42) is None


# ── extract_tool_calls_from_text ─────────────────────────────────────────
def test_extracts_a_fenced_json_tool_call():
    text = 'Sure!\n```json\n{"name": "aria_status", "arguments": {}}\n```'
    calls = extract_tool_calls_from_text(text, KNOWN)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "aria_status"
    assert calls[0]["function"]["arguments"] == {}


def test_extracts_an_unfenced_json_object():
    text = '{"name": "read_session", "arguments": {"id": "s1"}}'
    calls = extract_tool_calls_from_text(text, KNOWN)
    assert calls[0]["function"]["name"] == "read_session"
    assert calls[0]["function"]["arguments"] == {"id": "s1"}


def test_extracts_function_wrapped_shape_with_string_args():
    text = '```\n{"function": {"name": "read_session", "arguments": "{\\"id\\": \\"s1\\"}"}}\n```'
    calls = extract_tool_calls_from_text(text, KNOWN)
    assert calls[0]["function"]["name"] == "read_session"
    assert calls[0]["function"]["arguments"] == {"id": "s1"}


def test_never_invents_a_call_for_an_unknown_tool():
    text = '```json\n{"name": "delete_everything", "arguments": {}}\n```'
    assert extract_tool_calls_from_text(text, KNOWN) == []


def test_plain_prose_yields_no_call():
    assert extract_tool_calls_from_text("I think you should check your status.", KNOWN) == []


def test_dedupes_repeated_identical_calls():
    text = ('```json\n{"name": "aria_status", "arguments": {}}\n```\n'
            '```json\n{"name": "aria_status", "arguments": {}}\n```')
    assert len(extract_tool_calls_from_text(text, KNOWN)) == 1


# ── normalize_response ───────────────────────────────────────────────────
def test_structured_response_passes_through_untouched():
    resp = {"message": {"content": "", "tool_calls": [
        {"function": {"name": "aria_status", "arguments": {}}}]}}
    out = normalize_response(resp, KNOWN)
    assert out["message"]["tool_calls"][0]["function"]["name"] == "aria_status"
    assert "_bridged" not in out["message"]  # large-model path: no rescue flag


def test_structured_response_string_args_get_coerced():
    resp = {"message": {"content": "", "tool_calls": [
        {"function": {"name": "read_session", "arguments": '{"id": "s1"}'}}]}}
    out = normalize_response(resp, KNOWN)
    assert out["message"]["tool_calls"][0]["function"]["arguments"] == {"id": "s1"}


def test_small_model_text_call_is_rescued_into_structure():
    resp = {"message": {"content": '```json\n{"name": "list_objectives", "arguments": {}}\n```'}}
    out = normalize_response(resp, KNOWN)
    tcs = out["message"]["tool_calls"]
    assert tcs[0]["function"]["name"] == "list_objectives"
    assert out["message"]["_bridged"] is True


def test_normalize_does_not_mutate_input():
    resp = {"message": {"content": '{"name": "aria_status", "arguments": {}}'}}
    _ = normalize_response(resp, KNOWN)
    assert "tool_calls" not in resp["message"]  # original untouched


def test_normalize_is_safe_on_junk_input():
    assert normalize_response({}, KNOWN) == {}
    assert normalize_response({"message": "not-a-dict"}, KNOWN) == {"message": "not-a-dict"}


# ── bridge_report (the "bridge doctor") ──────────────────────────────────
def test_bridge_report_counts_structured_vs_bridged_vs_empty():
    responses = [
        normalize_response({"message": {"content": "", "tool_calls": [
            {"function": {"name": "aria_status", "arguments": {}}}]}}, KNOWN),
        normalize_response({"message": {"content": '{"name": "aria_status", "arguments": {}}'}}, KNOWN),
        normalize_response({"message": {"content": "just talking, no call"}}, KNOWN),
    ]
    rep = bridge_report(responses, KNOWN)
    assert rep["structured"] == 1
    assert rep["bridged"] == 1
    assert rep["no_tool_call"] == 1
    assert rep["total"] == 3
    assert abs(rep["bridged_fraction"] - 1 / 3) < 1e-9
    assert rep["connecting"] is True


# ── edge-case depth (full-system-scan hardening, 2026-07-11) ─────────────
def test_arguments_as_a_json_array_coerces_to_empty_not_crash():
    r = normalize_response(
        {"message": {"content": '{"name":"aria_status","arguments":[1,2,3]}'}}, KNOWN)
    assert r["message"]["tool_calls"][0]["function"]["arguments"] == {}


def test_two_tool_calls_in_one_json_list_are_both_rescued():
    txt = ('```json\n[{"name":"aria_status","arguments":{}},'
           '{"name":"read_session","arguments":{"id":"x"}}]\n```')
    calls = extract_tool_calls_from_text(txt, KNOWN)
    assert len(calls) == 2


def test_valid_json_that_is_not_a_tool_call_is_left_alone():
    r = normalize_response({"message": {"content": '{"answer": 42}'}}, KNOWN)
    assert "tool_calls" not in r["message"]


def test_empty_tool_calls_list_then_rescue_from_content():
    r = normalize_response(
        {"message": {"content": '{"name":"aria_status","arguments":{}}',
                     "tool_calls": []}}, KNOWN)
    assert r["message"].get("_bridged") is True


def test_none_content_does_not_crash():
    r = normalize_response({"message": {"content": None}}, KNOWN)
    assert "tool_calls" not in r["message"]


def test_huge_content_no_false_match_no_crash():
    r = normalize_response({"message": {"content": "word " * 50000}}, KNOWN)
    assert "tool_calls" not in r["message"]


def test_tool_call_fenced_language_tag():
    calls = extract_tool_calls_from_text(
        '```tool_call\n{"name":"aria_status","arguments":{}}\n```', KNOWN)
    assert len(calls) == 1
