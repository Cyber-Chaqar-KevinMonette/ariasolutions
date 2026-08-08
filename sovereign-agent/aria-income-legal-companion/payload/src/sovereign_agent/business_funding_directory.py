"""business_funding_directory.py — curated, verified reference for
business loans and funding programs (the static half of "income securing";
grants_tracker.py is the live-polled half via the real grants.gov API).

Kevin (2026-08-01): "add a category for business loans... income securing
category... for consumer law, loans, and other stuff" (clarified: loans +
grants + incentive programs, "all the above"). SBA program names/purposes
verified against sba.gov 2026-08-01 — same discipline as
real_estate_connections.py: only include what's independently verifiable
as real, not restated from memory.
"""
from __future__ import annotations

from dataclasses import dataclass


__all__ = ["FundingOption", "SBA_PROGRAMS", "STATE_INCENTIVE_PORTALS", "GENERAL_LENDERS"]


@dataclass(frozen=True)
class FundingOption:
    name: str
    url: str
    note: str


# Verified 2026-08-01 (sba.gov) — official U.S. Small Business
# Administration loan programs, government-guaranteed through private
# lenders (SBA doesn't lend directly for these).
SBA_PROGRAMS: tuple[FundingOption, ...] = (
    FundingOption(
        "SBA 7(a) Loan", "https://www.sba.gov/funding-programs/loans/7a-loans",
        "SBA's flagship, most flexible general-purpose loan — working "
        "capital, equipment, real estate, expansion. Government-guaranteed "
        "via private lenders, up to $5M."),
    FundingOption(
        "SBA 504 Loan", "https://www.sba.gov/funding-programs/loans/504-loans",
        "Long-term, fixed-rate financing for major fixed assets (real "
        "estate, heavy equipment) via a Certified Development Company + "
        "private lender — built for growth/expansion, not working capital."),
    FundingOption(
        "SBA Microloan", "https://www.sba.gov/funding-programs/loans/microloans",
        "Up to $50,000 (average ~$13,000) for startups and underserved "
        "businesses — smaller-scale needs than 7(a)/504, delivered through "
        "nonprofit community lenders."),
)

# Real, live, open state grant/incentive portals (a stretch beyond
# grants.gov's federal-only scope) — noted as reference, not integrated
# as live trackers.
STATE_INCENTIVE_PORTALS: tuple[FundingOption, ...] = (
    FundingOption(
        "California Grants Portal", "https://www.grants.ca.gov",
        "Statewide, mandated by the 2018 Grant Information Act — every CA "
        "state grant opportunity in one place, updated daily."),
    FundingOption(
        "NY Database of Economic Incentives", "https://esd.ny.gov/database-economic-incentives",
        "New York state's searchable database of business incentive "
        "programs (tax credits, grants, financing)."),
)

# General (non-SBA) small-business lending categories — informational
# only, not a live-polled market (loan rates/offers change per-application,
# not something to alert on the way a retail restock does).
GENERAL_LENDERS: tuple[FundingOption, ...] = (
    FundingOption(
        "Your local/regional bank or credit union", "",
        "Often the best rate for an established business with real "
        "revenue history — start here before alternative lenders."),
    FundingOption(
        "SCORE (free SBA-partnered mentorship)", "https://www.score.org",
        "Free business mentoring + loan-readiness help — a real, "
        "no-cost resource before shopping lenders."),
)
