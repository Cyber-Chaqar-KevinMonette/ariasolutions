"""test_real_estate_deal_analyzer.py — real math, hand-verified where the
inputs are clean round numbers; invariant checks for the general case."""
from __future__ import annotations

from sovereign_agent.real_estate_deal_analyzer import (
    analyze_deal, estimate_rent_range,
)


def test_estimate_rent_range_is_the_1pct_rule():
    low, mid, high = estimate_rent_range(200000)
    assert low == 1600.0     # 0.8%
    assert mid == 2000.0     # 1.0%
    assert high == 2400.0    # 1.2%
    assert low < mid < high


def test_estimate_rent_range_zero_price():
    assert estimate_rent_range(0) == (0.0, 0.0, 0.0)


def test_analyze_deal_hand_verified_zero_interest_case():
    """purchase=100000, 20% down (=20000 down, 80000 loan), 0% interest,
    10yr term -> monthly P&I = 80000/120 = 666.67 exactly. All rents set
    to 1000/mo with every expense knob at 0 so cash flow, cap rate,
    cash-on-cash, and payback are all hand-verifiable clean numbers."""
    result = analyze_deal(
        100000, 1000, 1000, 1000,
        down_payment_pct=0.20, interest_rate_pct=0.0, loan_term_years=10.0,
        closing_costs=0.0, rehab_costs=0.0, property_tax_annual=0.0,
        insurance_annual=0.0, hoa_monthly=0.0, vacancy_rate_pct=0.0,
        maintenance_pct=0.0, property_mgmt_pct=0.0,
    )

    assert result.down_payment == 20000.0
    assert result.loan_amount == 80000.0
    assert result.monthly_principal_and_interest == 666.67
    assert result.total_cash_invested == 20000.0

    mid = next(s for s in result.scenarios if s.scenario.label == "mid")
    assert mid.monthly_cash_flow == 333.33
    assert mid.cap_rate_pct == 12.0
    assert mid.cash_on_cash_pct == 20.0
    assert mid.payback_months == 60.0


def test_analyze_deal_higher_rent_scenarios_are_strictly_better():
    result = analyze_deal(
        250000, 1500, 2000, 2500,
        down_payment_pct=0.20, interest_rate_pct=6.5, loan_term_years=30.0,
        property_tax_annual=3000, insurance_annual=1200, vacancy_rate_pct=5.0,
        maintenance_pct=5.0,
    )
    low, mid, high = result.scenarios
    assert low.monthly_cash_flow < mid.monthly_cash_flow < high.monthly_cash_flow
    assert low.cap_rate_pct < mid.cap_rate_pct < high.cap_rate_pct
    # payback should shrink (or stay None->real) as rent climbs
    if low.payback_months is not None and high.payback_months is not None:
        assert high.payback_months < low.payback_months


def test_analyze_deal_negative_cash_flow_has_no_payback():
    """A rent too low to cover P&I + expenses never 'pays itself off' —
    payback_months and cash_on_cash_pct must be None, not a nonsense
    negative duration."""
    result = analyze_deal(
        500000, 500, 600, 700,     # rent nowhere near covering a $500k loan
        down_payment_pct=0.20, interest_rate_pct=7.0, loan_term_years=30.0,
    )
    for scenario in result.scenarios:
        assert scenario.monthly_cash_flow < 0
        assert scenario.payback_months is None


def test_analyze_deal_zero_cash_invested_has_no_cash_on_cash():
    result = analyze_deal(
        100000, 1000, 1000, 1000,
        down_payment_pct=0.0, interest_rate_pct=0.0, loan_term_years=10.0,
        closing_costs=0.0, rehab_costs=0.0,
    )
    assert result.total_cash_invested == 0.0
    for scenario in result.scenarios:
        assert scenario.cash_on_cash_pct is None
