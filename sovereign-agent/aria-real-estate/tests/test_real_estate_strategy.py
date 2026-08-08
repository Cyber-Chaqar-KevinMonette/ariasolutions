"""test_real_estate_strategy.py — the deterministic keyword-rule table."""
from __future__ import annotations

from sovereign_agent.real_estate_deal_analyzer import analyze_deal
from sovereign_agent.real_estate_strategy import suggest_strategy


def test_pre_foreclosure_signal_suggests_subject_to():
    text = "Owner is behind on payments and facing foreclosure, needs to sell fast."
    result = suggest_strategy(text)
    assert "subject-to" in result.lower()


def test_inherited_signal_suggests_seller_financing():
    result = suggest_strategy("Inherited property from probate, heirs want it gone.")
    assert "seller financing" in result.lower()


def test_as_is_signal_suggests_hard_money_brrrr():
    result = suggest_strategy("Handyman special, needs work, selling as-is.")
    assert "hard-money" in result.lower() or "brrrr" in result.lower()


def test_motivated_seller_signal_suggests_conventional_cash():
    result = suggest_strategy("Motivated seller, priced to sell, must sell this week.")
    assert "conventional" in result.lower() or "cash" in result.lower()


def test_no_signal_falls_back_to_default():
    result = suggest_strategy("Charming 3br home in a quiet neighborhood, well maintained.")
    assert "no strong distress signal" in result.lower()


def test_pre_foreclosure_wins_over_as_is_when_both_present():
    """Ordered rule table: the more actionable (subject-to) signal wins
    over the more generic (as-is/hard-money) one when both appear."""
    text = "Facing foreclosure, needs work, as-is sale."
    result = suggest_strategy(text)
    assert "subject-to" in result.lower()


def test_negative_cash_flow_analysis_appends_caution():
    analysis = analyze_deal(500000, 500, 600, 700, down_payment_pct=0.20,
                             interest_rate_pct=7.0, loan_term_years=30.0)
    result = suggest_strategy("Motivated seller, must sell.", analysis)
    assert "caution" in result.lower()
    assert "doesn't cash-flow" in result.lower()


def test_positive_cash_flow_analysis_has_no_caution():
    analysis = analyze_deal(100000, 1500, 1500, 1500, down_payment_pct=0.20,
                             interest_rate_pct=0.0, loan_term_years=10.0)
    result = suggest_strategy("Motivated seller, must sell.", analysis)
    assert "caution" not in result.lower()
