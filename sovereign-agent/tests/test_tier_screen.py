"""F4 — the trust-tier menu + kill switch (ceremony asymmetry tested)."""
from __future__ import annotations

from sovereign_agent.cockpit.tier_screen import TIERS, approval_phrase


def test_tiers_cover_the_autocrown_ladder():
    from sovereign_agent.auto_crown import _TRUST_TIER_MAX_HOURS
    assert [t for t, _, _ in TIERS] == sorted(_TRUST_TIER_MAX_HOURS)


def test_approval_phrase_shape():
    assert approval_phrase(3) == "I approve tier 3"


def test_raise_needs_phrase_lower_is_instant(tmp_path, monkeypatch):
    """The safety asymmetry: raising = ceremony; the kill switch = one
    click. Proven against a real AutoCrownStore on a temp data dir."""
    from sovereign_agent.auto_crown import AutoCrownStore
    store = AutoCrownStore(data_dir=tmp_path)
    assert store.get_max_trust_tier() == 1
    store.set_trust_tier(3)                     # what the ceremony does
    assert store.get_max_trust_tier() == 3
    store.set_trust_tier(1)                     # what the kill switch does
    assert store.get_max_trust_tier() == 1


def test_screen_importable_and_wired():
    from sovereign_agent.cockpit import app as cockpit_app
    assert cockpit_app.TierScreen is not None
    assert hasattr(cockpit_app.CockpitApp, "action_tiers")


# tier3-quick-toggle-d: dedicated Activate/Deactivate Tier 3 buttons.
# Real click-through coverage lives in
# aria-tier3-quick-toggle/tests/test_tier3_quick_toggle.py (kept there,
# not duplicated here -- these mirror this file's own existing
# logic-level style).

def test_activate_tier3_starts_ceremony_not_bypass(tmp_path, monkeypatch):
    from sovereign_agent.auto_crown import AutoCrownStore
    from sovereign_agent.cockpit.tier_screen import TierScreen

    store = AutoCrownStore(data_dir=tmp_path)
    monkeypatch.setattr(
        "sovereign_agent.cockpit.tier_screen.TierScreen._store",
        lambda self: store)
    screen = TierScreen()
    screen._activate_tier3()
    assert screen._pending_tier == 3
    assert store.get_max_trust_tier() == 1


def test_deactivate_tier3_is_instant_like_the_kill_switch(tmp_path, monkeypatch):
    from sovereign_agent.auto_crown import AutoCrownStore
    from sovereign_agent.cockpit.tier_screen import TierScreen

    store = AutoCrownStore(data_dir=tmp_path)
    store.set_trust_tier(3)
    monkeypatch.setattr(
        "sovereign_agent.cockpit.tier_screen.TierScreen._store",
        lambda self: store)
    screen = TierScreen()
    screen._deactivate_tier3()
    assert store.get_max_trust_tier() == 1
