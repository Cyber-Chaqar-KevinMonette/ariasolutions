"""Tests for suggestions.py — user suggestions + donation-weighted priority."""
from __future__ import annotations

import pytest

from sovereign_agent.suggestions import (
    VOTE_WEIGHT_CENTS,
    add_suggestion,
    boost,
    compose_suggestions_report,
    delete,
    is_suggestions_query,
    list_all,
    load,
    set_status,
    vote,
)


def test_add_and_load(tmp_path):
    s = add_suggestion(tmp_path, "Add a Twitch live-alert bot", author="Kev",
                       target="Feed Bot", kind="addon")
    assert s.id and s.status == "open" and s.kind == "addon"
    got = load(s.id, tmp_path)
    assert got is not None and got.text == "Add a Twitch live-alert bot"


def test_add_requires_text(tmp_path):
    with pytest.raises(ValueError):
        add_suggestion(tmp_path, "   ")


def test_priority_is_donation_forward(tmp_path):
    free = add_suggestion(tmp_path, "free idea")
    for _ in range(10):
        vote(free.id, tmp_path)                    # 10 votes = 200 cents priority
    paid = add_suggestion(tmp_path, "boosted idea")
    boost(paid.id, tmp_path, cents=500)            # $5 = 500 cents
    ranked = list_all(tmp_path)
    assert ranked[0].id == paid.id                 # a real donation outranks votes
    assert load(free.id, tmp_path).priority == 10 * VOTE_WEIGHT_CENTS


def test_votes_still_count_and_never_negative(tmp_path):
    s = add_suggestion(tmp_path, "x")
    vote(s.id, tmp_path)
    vote(s.id, tmp_path, delta=-5)
    assert load(s.id, tmp_path).votes == 0         # clamped at 0


def test_boost_accumulates(tmp_path):
    s = add_suggestion(tmp_path, "x")
    boost(s.id, tmp_path, cents=300)
    boost(s.id, tmp_path, cents=200)
    assert load(s.id, tmp_path).donation_cents == 500


def test_boost_ignores_nonpositive(tmp_path):
    s = add_suggestion(tmp_path, "x")
    boost(s.id, tmp_path, cents=0)
    boost(s.id, tmp_path, cents=-100)
    assert load(s.id, tmp_path).donation_cents == 0


def test_set_status_valid_and_invalid(tmp_path):
    s = add_suggestion(tmp_path, "x")
    set_status(s.id, tmp_path, "planned")
    assert load(s.id, tmp_path).status == "planned"
    with pytest.raises(ValueError):
        set_status(s.id, tmp_path, "bogus")


def test_list_filters_by_status(tmp_path):
    a = add_suggestion(tmp_path, "a")
    add_suggestion(tmp_path, "b")
    set_status(a.id, tmp_path, "done")
    assert [x.text for x in list_all(tmp_path, status="done")] == ["a"]


def test_delete(tmp_path):
    s = add_suggestion(tmp_path, "x")
    assert delete(s.id, tmp_path) is True
    assert delete(s.id, tmp_path) is False


def test_report_excludes_resolved(tmp_path):
    open_s = add_suggestion(tmp_path, "keep me open")
    done_s = add_suggestion(tmp_path, "already done")
    set_status(done_s.id, tmp_path, "done")
    out = compose_suggestions_report(tmp_path)
    assert "keep me open" in out and "already done" not in out


def test_report_empty(tmp_path):
    assert "No suggestions yet" in compose_suggestions_report(tmp_path)


def test_is_suggestions_query():
    assert is_suggestions_query("show me the community suggestions")
    assert is_suggestions_query("what should we build next")
    assert is_suggestions_query("any feature requests?")
    assert not is_suggestions_query("how are you today")
    # bare "any suggestions?" is left to next_report (what do you suggest I do)
    assert not is_suggestions_query("any suggestions?")
