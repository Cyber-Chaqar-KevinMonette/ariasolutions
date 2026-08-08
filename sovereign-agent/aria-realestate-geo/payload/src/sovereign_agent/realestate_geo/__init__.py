"""realestate_geo — state-categorized real estate verticals + forum-channel support.

realestate-geo-d (Kevin, 2026-08-03): "categories for each state and channels
for each county... each county channel gets a listings thread or panel" —
state-level real estate categories, one Discord forum channel per county,
one thread per new listing (per-county discovery feeds).

TN/KY sources verified live (Christian Co., Montgomery Co., Edmonson Co.).
VA/FL/CA are placeholders; real URLs must be curl-verified before shipping.

This module is STAGED — apply_realestate_geo.sh patches src/ files in place.
"""
from __future__ import annotations

__all__ = ["STATE_CATEGORIES", "COUNTY_VERTICALS"]

# Placeholder metadata. Real payload is in the apply script's patches.
STATE_CATEGORIES = ["REAL ESTATE — TN", "REAL ESTATE — VA", "REAL ESTATE — FL", "REAL ESTATE — CA"]
COUNTY_VERTICALS = {
    "REAL ESTATE — TN": ["realestate-tn-christian", "realestate-tn-montgomery", "realestate-tn-edmonson"],
    "REAL ESTATE — VA": ["realestate-va-virginiabeach"],  # TODO: curl-verify real URL
    "REAL ESTATE — FL": ["realestate-fl-miamidade"],      # TODO: curl-verify real URL
    "REAL ESTATE — CA": ["realestate-ca-losangeles"],     # TODO: curl-verify real URL
}
