"""Tests for cc_bridge — Claude Code in the cockpit, safe by construction.
Injected runners only; no test spawns a real subprocess.
"""
from __future__ import annotations

import json

from sovereign_agent.cc_bridge import (
    cc_ledger_path,
    render_result,
    run_cc,
)


def _runner(rc=0, out="", err=""):
    calls = {}

    def run(argv, cwd, timeout):
        calls["argv"], calls["cwd"], calls["timeout"] = argv, cwd, timeout
        return rc, out, err

    run.calls = calls
    return run


def _json_reply(text, cost=0.03, sid="abc123"):
    return json.dumps({"result": text, "total_cost_usd": cost,
                       "session_id": sid})


def test_happy_path_parses_json_and_ledgers(tmp_path):
    r = _runner(out=_json_reply("The bug is in delivery.py line 42."))
    res = run_cc("find the bug", runner=r, data_dir=tmp_path)
    assert res.ok and "delivery.py" in res.text
    assert res.cost_usd == 0.03 and res.session_id == "abc123"
    rec = json.loads(cc_ledger_path(tmp_path).read_text().splitlines()[0])
    assert rec["ok"] and rec["prompt"] == "find the bug"


def test_never_passes_the_permission_bypass_flag(tmp_path):
    """The safety line: normal permissions ALWAYS — propose-don't-act is
    structural, not a hope."""
    r = _runner(out=_json_reply("hi"))
    run_cc("x", runner=r, data_dir=tmp_path)
    argv = r.calls["argv"]
    assert argv[0] == "claude" and "-p" in argv
    assert not any("dangerously" in a or "skip-permissions" in a
                   for a in argv), argv
    assert argv[-2] == "--"                    # prompt can't become a flag


def test_empty_prompt_teaches_usage():
    res = run_cc("   ")
    assert not res.ok and "usage: /cc" in res.text


def test_failures_are_honest_never_raise(tmp_path):
    res = run_cc("x", runner=_runner(rc=127, err="claude CLI not found"),
                 data_dir=tmp_path)
    assert not res.ok and "not found" in res.text
    res2 = run_cc("x", runner=_runner(rc=124, err="timed out after 240s"),
                  data_dir=tmp_path)
    assert not res2.ok and "timed out" in res2.text


def test_unparseable_output_degrades_to_raw_text(tmp_path):
    res = run_cc("x", runner=_runner(out="plain words, not json"),
                 data_dir=tmp_path)
    assert res.ok and res.text == "plain words, not json"


def test_render_result_shows_meta():
    r = _runner(out=_json_reply("answer", cost=0.5))
    out = render_result(run_cc("x", runner=r))
    assert "🤝 Claude Code" in out and "$0.50" in out and "answer" in out


def test_long_prompt_is_bounded(tmp_path):
    r = _runner(out=_json_reply("ok"))
    run_cc("A" * 20000, runner=r, data_dir=tmp_path)
    sent = r.calls["argv"][-1]
    assert len(sent) == 8000                   # MAX_PROMPT clamp
