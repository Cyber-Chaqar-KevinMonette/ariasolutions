"""R4 tests — workflow-success patterns: distill, match, report."""
from __future__ import annotations

from dataclasses import dataclass, field

from sovereign_agent.success_patterns import (
    compose_success_report,
    goal_tokens,
    is_success_query,
    load_records,
    match_goal,
    record_outcome,
)


# minimal stand-ins for SessionState/Subtask (defensive getattr access)
@dataclass
class _Sub:
    status: str = "done"


@dataclass
class _Session:
    goal: str = "build a restock alert bot for pokemon cards"
    status: str = "done"
    session_id: str = "s1"
    subtasks: list = field(default_factory=lambda: [_Sub(), _Sub(), _Sub("pending")])
    created_at: str = "2026-07-13T01:00:00+00:00"
    updated_at: str = "2026-07-13T01:20:00+00:00"


def test_goal_tokens_drop_stopwords_and_dupes():
    toks = goal_tokens("Build a NEW restock bot — the restock bot for cards")
    assert "restock" in toks and "bot" in toks and "cards" in toks
    assert "the" not in toks and "build" not in toks and "new" not in toks
    assert toks.count("restock") == 1


def test_record_and_load_round_trip(tmp_path):
    rec = record_outcome(_Session(), tmp_path)
    assert rec is not None and rec.succeeded
    assert rec.subtasks_done == 2 and rec.subtasks_total == 3
    assert rec.duration_s == 1200.0
    got = load_records(tmp_path)
    assert len(got) == 1 and got[0].goal.startswith("build a restock")


def test_record_outcome_never_raises_on_garbage(tmp_path):
    assert record_outcome(object(), tmp_path) is None      # no fields at all
    assert record_outcome(_Session(goal=""), tmp_path) is None


def test_match_goal_finds_similar_wins_only(tmp_path):
    record_outcome(_Session(), tmp_path)                    # a win
    record_outcome(_Session(goal="build a restock watcher for pokemon plush",
                            status="halted", session_id="s2"), tmp_path)  # not a win
    matches = match_goal("restock bot for pokemon", data_dir=tmp_path)
    assert len(matches) == 1                                # only the success
    score, rec = matches[0]
    assert rec.session_id == "s1" and score > 0.2


def test_match_goal_empty_and_unrelated(tmp_path):
    record_outcome(_Session(), tmp_path)
    assert match_goal("", data_dir=tmp_path) == []
    assert match_goal("compose a symphony orchestra", data_dir=tmp_path) == []


def test_load_skips_torn_lines(tmp_path):
    record_outcome(_Session(), tmp_path)
    from sovereign_agent.success_patterns import patterns_path
    with open(patterns_path(tmp_path), "a", encoding="utf-8") as fh:
        fh.write("{torn\n")
    assert len(load_records(tmp_path)) == 1


def test_report_empty_and_with_goal(tmp_path):
    assert "No workflow history" in compose_success_report(data_dir=tmp_path)
    record_outcome(_Session(), tmp_path)
    out = compose_success_report("what usually works for a restock bot for pokemon?",
                                 data_dir=tmp_path)
    assert "Prior wins" in out and "restock" in out and "Advisory" in out
    general = compose_success_report(data_dir=tmp_path)
    assert "1 succeeded" in general or "succeeded (100%)" in general


def test_is_success_query_precise():
    assert is_success_query("what usually works for this?")
    assert is_success_query("have we done this before?")
    assert not is_success_query("how are you today")
    assert not is_success_query("what's in the shop?")
