"""modes_crown — declarative operator modes + her own inner stances +
the observatory window. (FABLE II · M6)

Staged; applied via apply_modes_crown.sh. See profiles.py (the mode
picker's profiles), stances.py (her safe inner postures), and
observatory.py (the watching window's gathered data).
"""
from __future__ import annotations

from .observatory import gather_observatory, gather_stress, render_observatory_text
from .profiles import (
    AUTO3H_CONFIRMATION, CrownError, ModeProfile, PROFILES,
    crown_armed, crown_wondering_allowed, current_profile,
    lease_remaining_seconds, set_crown_mode,
)
from .stances import SAFE_STANCES, cooling_down, current_stance, recent_stances, set_stance

__all__ = [
    "AUTO3H_CONFIRMATION", "CrownError", "ModeProfile", "PROFILES",
    "crown_armed", "crown_wondering_allowed", "current_profile",
    "lease_remaining_seconds", "set_crown_mode", "SAFE_STANCES",
    "cooling_down", "current_stance", "recent_stances", "set_stance",
    "gather_observatory", "gather_stress", "render_observatory_text",
]
