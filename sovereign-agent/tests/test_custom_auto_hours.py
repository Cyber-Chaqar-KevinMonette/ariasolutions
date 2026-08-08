"""Tests for custom-auto-hours-d.

Kevin, 2026-07-25: "a drop down menu for hours. Max 12. Min 1." Adds a
THIRD arming path alongside the two named profiles (auto-1h, auto-3h):
arm_custom_hours(hours) for anything in between/beyond them, composing
with the SAME trust-tier enforcement _arm_lease already has, and the
same duration-ceiling-raise-d change (tier 4 now 12h, not 8h).

_arm_lease is mocked throughout (matching this test file's own existing
convention of picking lease-free profiles to avoid touching the real,
singleton AutoCrownStore/work_interval state on this machine) so these
tests exercise arm_custom_hours()'s own logic without arming a real
auto session.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sovereign_agent.modes_crown.profiles import (
    CrownError, arm_custom_hours, current_profile, custom_hours_trust_tier,
)


def test_tier_4_ceiling_is_now_12_hours():
    from sovereign_agent.auto_crown import TRUST_TIER_MAX_HOURS
    assert TRUST_TIER_MAX_HOURS[4] == 12.0


def test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier():
    assert custom_hours_trust_tier(0.5) == 1
    assert custom_hours_trust_tier(1.0) == 1
    assert custom_hours_trust_tier(1.5) == 2
    assert custom_hours_trust_tier(3.0) == 3
    assert custom_hours_trust_tier(4.0) == 3
    assert custom_hours_trust_tier(5.0) == 4
    assert custom_hours_trust_tier(12.0) == 4


def test_arm_custom_hours_rejects_out_of_range():
    with pytest.raises(CrownError):
        arm_custom_hours(0.0)
    with pytest.raises(CrownError):
        arm_custom_hours(13.0)


def test_arm_custom_hours_builds_the_right_profile_and_persists_it(tmp_path):
    with patch("sovereign_agent.modes_crown.profiles._arm_lease",
              return_value="fake-lease-id") as arm_lease:
        profile = arm_custom_hours(0.75, data_dir=tmp_path)

    assert profile.mode_id == "auto-custom"
    assert profile.lease_seconds == int(0.75 * 3600)
    assert profile.trust_tier == 1
    arm_lease.assert_called_once()

    record = (tmp_path / "mode_crown.json").read_text()
    assert "auto-custom" in record
    assert '"profile"' in record


def test_arm_custom_hours_propagates_the_real_tier_refusal(tmp_path):
    """_arm_lease is where the real trust-tier check lives (via
    AutoCrownStore.start()) -- arm_custom_hours must not swallow it."""
    with patch("sovereign_agent.modes_crown.profiles._arm_lease",
              side_effect=CrownError("Trust tier 4 exceeds max allowed (1)")):
        with pytest.raises(CrownError):
            arm_custom_hours(6.0, data_dir=tmp_path)


def test_current_profile_reconstructs_an_armed_custom_profile(tmp_path):
    """The real bug this avoids: current_profile() used to only know the
    fixed PROFILES dict, so an armed 'auto-custom' would silently read
    back as 'work' -- losing the actual hours/tier that were armed."""
    with patch("sovereign_agent.modes_crown.profiles._arm_lease",
              return_value="fake-lease-id"):
        arm_custom_hours(0.5, data_dir=tmp_path)

    profile = current_profile(data_dir=tmp_path)
    assert profile.mode_id == "auto-custom"
    assert profile.lease_seconds == int(0.5 * 3600)
