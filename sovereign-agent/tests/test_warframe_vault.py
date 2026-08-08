"""vaulted-relics-d (Kevin, 2026-07-27): "Add a vaulted relics command
that shows all of the active warframe vaulted relics/warframes...
What relics go to what part of the warframe." Synthetic data shaped
exactly like the two real sources (warframe.market's vaulted relics +
Warframe-tagged set names, drops.warframestat.us's relic reward
tables) — live-verified before this module was written.
"""
from __future__ import annotations

from sovereign_agent.warframe_vault import RelicRef, build_vault_map


def test_maps_a_warframe_part_to_its_real_vaulted_relic():
    vaulted = [("Axi", "H3")]
    rewards = {("Axi", "H3"): ["Hydroid Prime Systems Blueprint",
                               "Burston Prime Barrel"]}
    names = ["Hydroid Prime"]   # weapons (Burston) never in warframe_names
    out = build_vault_map(vaulted, rewards, names)
    assert out == {"Hydroid Prime": {"Systems": [RelicRef("Axi", "H3")]}}


def test_ignores_weapon_parts_even_with_the_same_blueprint_suffix():
    # a real ambiguity: "Kronen Prime Blueprint" ends in "Blueprint"
    # just like a Warframe's own main blueprint would, but Kronen isn't
    # a real Warframe name — must never be misfiled as one
    vaulted = [("Axi", "H3")]
    rewards = {("Axi", "H3"): ["Kronen Prime Blueprint",
                               "Cernos Prime Grip"]}
    names = ["Hydroid Prime"]     # Kronen/Cernos are weapons, not in this list
    out = build_vault_map(vaulted, rewards, names)
    assert out == {}


def test_ignores_non_blueprint_junk_rewards():
    vaulted = [("Axi", "H3")]
    rewards = {("Axi", "H3"): ["2X Forma Blueprint", "Endo"]}
    names = ["Hydroid Prime"]
    assert build_vault_map(vaulted, rewards, names) == {}


def test_a_relic_never_double_lists_for_the_same_part():
    # e.g. Intact + Radiant states of the same relic both passed in by
    # mistake — must not duplicate the relic ref for the same part
    vaulted = [("Axi", "H3"), ("Axi", "H3")]
    rewards = {("Axi", "H3"): ["Hydroid Prime Systems Blueprint"]}
    out = build_vault_map(vaulted, rewards, ["Hydroid Prime"])
    assert out["Hydroid Prime"]["Systems"] == [RelicRef("Axi", "H3")]


def test_same_part_from_two_different_vaulted_relics_lists_both():
    vaulted = [("Axi", "H3"), ("Meso", "F2")]
    rewards = {
        ("Axi", "H3"): ["Hydroid Prime Systems Blueprint"],
        ("Meso", "F2"): ["Hydroid Prime Systems Blueprint"],
    }
    out = build_vault_map(vaulted, rewards, ["Hydroid Prime"])
    assert set(out["Hydroid Prime"]["Systems"]) == {
        RelicRef("Axi", "H3"), RelicRef("Meso", "F2")}


def test_longer_warframe_name_wins_over_a_shorter_name_that_is_a_prefix():
    # a deliberately adversarial case: two real names where one is a
    # prefix of a longer one — must not misfile onto the shorter match
    vaulted = [("Axi", "X1")]
    rewards = {("Axi", "X1"): ["Nova Prime Systems Blueprint"]}
    names = ["Nova Prime", "Nova"]   # "Nova" is a fabricated shorter decoy here
    out = build_vault_map(vaulted, rewards, names)
    assert list(out.keys()) == ["Nova Prime"]


def test_relic_with_no_rewards_mapped_is_silently_skipped():
    vaulted = [("Axi", "Unknown")]
    out = build_vault_map(vaulted, {}, ["Hydroid Prime"])
    assert out == {}


def test_relic_ref_label():
    assert RelicRef("Axi", "H3").label == "Axi H3"
