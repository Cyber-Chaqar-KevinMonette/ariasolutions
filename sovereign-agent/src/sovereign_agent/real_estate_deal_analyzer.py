"""real_estate_deal_analyzer.py — the long-term math for a real estate lead.

Kevin, 2026-07-28/29: "have the bot do the long term math when it will
pay itself off, how much profits you will be making monthly at what rent
ranges." Pure math, no I/O, no network — every number here is a real
computation from the inputs given, never a fabricated figure. Free: no
paid rent-comp API is required, though a real one can be plugged in
later — `estimate_rent_range` is only a fallback for leads with no real
comp yet, clearly labeled as a rough heuristic (the "1% rule"), never
presented as a real appraisal.

This is what gets attached to a lead alert and what the "secure-deals"
channel filters by (see `real_estate_requirements.requirement_passes`).
"""
from __future__ import annotations

from dataclasses import dataclass


__all__ = [
    "RentScenario",
    "ScenarioResult",
    "DealAnalysis",
    "estimate_rent_range",
    "analyze_deal",
]


@dataclass(frozen=True)
class RentScenario:
    label: str          # "low" | "mid" | "high"
    monthly_rent: float


@dataclass(frozen=True)
class ScenarioResult:
    scenario: RentScenario
    monthly_cash_flow: float
    cap_rate_pct: float
    cash_on_cash_pct: float | None      # None if total cash invested is 0
    payback_months: float | None        # None if cash flow never turns positive


@dataclass(frozen=True)
class DealAnalysis:
    purchase_price: float
    down_payment: float
    loan_amount: float
    monthly_principal_and_interest: float
    total_cash_invested: float
    scenarios: list[ScenarioResult]


def estimate_rent_range(purchase_price: float) -> tuple[float, float, float]:
    """Free, no-API rent estimate for a lead with no real comp yet — the
    "1% rule" heuristic real-estate investors use as a fast gut check
    (0.8%/1.0%/1.2% of price per month for low/mid/high). This is a rough
    estimate, not a real appraisal — callers should prefer a real rent
    comp when one is available and only fall back to this."""
    if purchase_price <= 0:
        return (0.0, 0.0, 0.0)
    return (
        round(purchase_price * 0.008, 2),
        round(purchase_price * 0.010, 2),
        round(purchase_price * 0.012, 2),
    )


def _monthly_pi(loan_amount: float, interest_rate_pct: float, loan_term_years: float) -> float:
    """Standard amortization formula for monthly principal + interest."""
    if loan_amount <= 0:
        return 0.0
    monthly_rate = (interest_rate_pct / 100.0) / 12.0
    n = loan_term_years * 12.0
    if monthly_rate == 0:
        return loan_amount / n
    return loan_amount * monthly_rate / (1 - (1 + monthly_rate) ** -n)


def _analyze_scenario(
    label: str, monthly_rent: float, *, monthly_pi: float, monthly_tax: float,
    monthly_insurance: float, hoa_monthly: float, vacancy_rate_pct: float,
    maintenance_pct: float, property_mgmt_pct: float, purchase_price: float,
    total_cash_invested: float,
) -> ScenarioResult:
    scenario = RentScenario(label=label, monthly_rent=monthly_rent)

    vacancy_loss = monthly_rent * (vacancy_rate_pct / 100.0)
    effective_rent = monthly_rent - vacancy_loss
    maintenance = monthly_rent * (maintenance_pct / 100.0)
    mgmt = monthly_rent * (property_mgmt_pct / 100.0)
    operating_expenses = monthly_tax + monthly_insurance + hoa_monthly + maintenance + mgmt

    noi_monthly = effective_rent - operating_expenses
    cash_flow = noi_monthly - monthly_pi

    cap_rate_pct = (noi_monthly * 12.0 / purchase_price * 100.0) if purchase_price > 0 else 0.0

    cash_on_cash_pct = (
        (cash_flow * 12.0 / total_cash_invested * 100.0)
        if total_cash_invested > 0 else None
    )
    payback_months = (
        (total_cash_invested / cash_flow) if cash_flow > 0 and total_cash_invested > 0 else None
    )

    return ScenarioResult(
        scenario=scenario,
        monthly_cash_flow=round(cash_flow, 2),
        cap_rate_pct=round(cap_rate_pct, 2),
        cash_on_cash_pct=round(cash_on_cash_pct, 2) if cash_on_cash_pct is not None else None,
        payback_months=round(payback_months, 1) if payback_months is not None else None,
    )


def analyze_deal(
    purchase_price: float, rent_low: float, rent_mid: float, rent_high: float, *,
    down_payment_pct: float = 0.20, interest_rate_pct: float = 7.0,
    loan_term_years: float = 30.0, closing_costs: float = 0.0, rehab_costs: float = 0.0,
    property_tax_annual: float = 0.0, insurance_annual: float = 0.0,
    hoa_monthly: float = 0.0, vacancy_rate_pct: float = 5.0,
    maintenance_pct: float = 5.0, property_mgmt_pct: float = 0.0,
) -> DealAnalysis:
    """The long-term math for one lead: monthly P&I, then per rent
    scenario (low/mid/high) the monthly cash flow, cap rate, cash-on-cash
    return, and payback period (months to recoup total cash invested).
    Every figure is computed from the given inputs — never fabricated."""
    down_payment = purchase_price * down_payment_pct
    loan_amount = purchase_price - down_payment
    monthly_pi = _monthly_pi(loan_amount, interest_rate_pct, loan_term_years)
    total_cash_invested = down_payment + closing_costs + rehab_costs

    monthly_tax = property_tax_annual / 12.0
    monthly_insurance = insurance_annual / 12.0

    scenarios = [
        _analyze_scenario(
            label, rent, monthly_pi=monthly_pi, monthly_tax=monthly_tax,
            monthly_insurance=monthly_insurance, hoa_monthly=hoa_monthly,
            vacancy_rate_pct=vacancy_rate_pct, maintenance_pct=maintenance_pct,
            property_mgmt_pct=property_mgmt_pct, purchase_price=purchase_price,
            total_cash_invested=total_cash_invested,
        )
        for label, rent in (("low", rent_low), ("mid", rent_mid), ("high", rent_high))
    ]

    return DealAnalysis(
        purchase_price=purchase_price,
        down_payment=round(down_payment, 2),
        loan_amount=round(loan_amount, 2),
        monthly_principal_and_interest=round(monthly_pi, 2),
        total_cash_invested=round(total_cash_invested, 2),
        scenarios=scenarios,
    )
