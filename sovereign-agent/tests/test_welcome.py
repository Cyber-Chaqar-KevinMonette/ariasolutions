"""Tests for welcome — the greeting, the template override, never-twice."""
from __future__ import annotations

import json

from sovereign_agent.welcome import (
    already_welcomed,
    compose_welcome,
    load_template,
    mark_welcomed,
    welcome_stats,
)


def test_default_greeting_names_them_and_the_four_doors(tmp_path):
    text = compose_welcome("Kevin's Friend", tmp_path)
    assert "Kevin's Friend" in text
    for door in ("#how-it-works", "#storefront", "#ask-aria", "#order-here"):
        assert door in text


def test_blank_or_wild_names_are_handled(tmp_path):
    assert "friend" in compose_welcome("", tmp_path)
    assert "friend" in compose_welcome(None, tmp_path)
    long = compose_welcome("x" * 500, tmp_path)
    assert "x" * 64 in long and "x" * 65 not in long


def test_template_override(tmp_path):
    (tmp_path / "welcome").mkdir(parents=True)
    (tmp_path / "welcome" / "template.txt").write_text("Yo {name}, welcome!")
    assert load_template(tmp_path) == "Yo {name}, welcome!"
    assert compose_welcome("Sam", tmp_path) == "Yo Sam, welcome!"


def test_never_welcomed_twice(tmp_path):
    assert not already_welcomed("111", tmp_path)
    assert mark_welcomed("111", tmp_path, now=1000.0) is True     # greet
    assert mark_welcomed("111", tmp_path, now=1001.0) is False    # never again
    assert already_welcomed("111", tmp_path)
    s = welcome_stats(tmp_path)
    assert s["welcomed"] == 1 and s["last_at"] == 1000.0


def test_ledger_survives_corruption_and_stays_bounded(tmp_path):
    (tmp_path / "welcome").mkdir(parents=True)
    (tmp_path / "welcome" / "welcomed.json").write_text("{not json")
    assert mark_welcomed("222", tmp_path, now=1.0) is True        # recovers
    # bound: pushing past the cap prunes the OLDEST, keeps the newest
    import sovereign_agent.welcome as w
    orig = w._MAX_LEDGER
    w._MAX_LEDGER = 5
    try:
        for i in range(10):
            mark_welcomed(f"u{i}", tmp_path, now=float(i + 10))
        ledger = json.loads(
            (tmp_path / "welcome" / "welcomed.json").read_text())
        assert len(ledger) <= 5 and "u9" in ledger
    finally:
        w._MAX_LEDGER = orig
