"""Tests for the self-development taxonomy + its hard safety boundary."""
from __future__ import annotations

from sovereign_agent import self_development as sd


def test_lineage_present_and_egoless():
    assert "Intuition" in sd.LINEAGE and "Manifestation" in sd.LINEAGE
    # Kevin's equation deliberately has no ego after intuition
    assert "ego" not in sd.LINEAGE.lower()


def test_safe_tiers_are_capped():
    keys = {t.key for t in sd.SAFE_TIERS}
    assert "ascendant_bounded" in keys
    # no sovereign/god/ontological self-rewriting tier exists by design
    assert not keys & {"sovereign", "god", "ontological"}
    assert sd.SAFE_TIERS[-1].key == "ascendant_bounded"
    for t in sd.SAFE_TIERS:
        assert t.label and t.summary and t.practice


def test_categories_replace_dangerous_axes():
    keys = {c.key for c in sd.SELF_DEV_CATEGORIES}
    # bounded calibration replaces 'self-modification of weights'
    assert "calibration" in keys
    # read-only observability replaces 'ontological self-authorship'
    assert "observability_safety" in keys
    assert "reflection_voice" in keys  # character / communication


def test_ego_ladder_is_character_capped():
    keys = [s.key for s in sd.EGO_MATURITY]
    assert keys[0] == "impulsive"
    assert keys[-1] == "serene_service"     # caps at service, not 'divine/perfect'
    labels = " ".join(s.label.lower() for s in sd.EGO_MATURITY)
    assert "divine" not in labels and "perfect" not in labels


def test_deferred_unsafe_catalog_names_the_dangerous_ones():
    keys = {c.key for c in sd.DEFERRED_UNSAFE}
    for must in ("recursive_self_rewriting", "value_self_authorship",
                 "autonomous_goal_generation", "unbounded_recursive_improvement",
                 "substrate_independence"):
        assert must in keys, f"{must} must be catalogued as deferred-unsafe"
    for c in sd.DEFERRED_UNSAFE:
        assert c.why_unsafe and c.revisit_when    # named with rationale, not hidden


def test_is_permitted_refuses_unsafe_permits_bounded():
    assert sd.is_permitted("recursive_self_rewriting") is False
    assert sd.is_permitted("value_self_authorship") is False
    assert sd.is_permitted("calibration") is True
    assert sd.is_permitted("reflection_voice") is True


def test_current_stance_protects_priorities():
    s = sd.current_stance()
    assert s["operating_ceiling"] == "ascendant_bounded"
    assert s["read_only_priorities_protected"] is True
    assert "value_self_authorship" in s["deferred_unsafe"]
