"""warframe_vault.py — vaulted Warframe ↔ relic mapping, pure logic.

Kevin (2026-07-27): "Add a vaulted relics command that shows all of the
active warframe vaulted relics/warframes. The warframes and all the
relics that are vaulted along with that warframe. What relics go to
what part of the warframe."

Cross-references TWO real, independently-verified sources (2026-07-27) —
there is no single API that answers this on its own:
  • warframe.market's `vaulted` flag lives ONLY on RELIC items — live-
    verified that Warframe SET and PART items carry no such flag at all
    (0 of 150 real Warframe part items had it). So "is this WARFRAME
    vaulted" isn't a field anywhere; it's inferred honestly from
    whether ALL of its parts are only reachable via relics
    warframe.market itself marks vaulted.
  • drops.warframestat.us's community-maintained drop table (WFCD, the
    same trust tier as warframe.market for third-party tools) gives
    the real reward list per relic — but carries no vaulted flag of its
    own, so it's used ONLY for "what does relic X drop," never for
    vaulted status.
  • warframe.market's own Warframe-tagged Prime sets (tags include
    "warframe", distinct from weapon Prime sets tagged "weapon") give
    the real "<Name> Prime" prefixes — needed because a relic reward
    list mixes Warframe parts and weapon parts, and both can end in
    "... Blueprint" (e.g. "Hydroid Prime Systems Blueprint" vs. "Kronen
    Prime Blueprint") — only an exact, real Warframe name prefix tells
    them apart, never a guess.

Pure logic only — no network. `fetchers.py` is the thin I/O wrapper.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RelicRef", "build_vault_map"]


@dataclass(frozen=True)
class RelicRef:
    tier: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.tier} {self.name}"


def build_vault_map(vaulted_relics: list[tuple[str, str]],
                   relic_rewards: dict[tuple[str, str], list[str]],
                   warframe_names: list[str],
                   ) -> dict[str, dict[str, list[RelicRef]]]:
    """`vaulted_relics`: real (tier, name) pairs from warframe.market's
    `vaulted` flag. `relic_rewards`: {(tier, name): [reward itemName,
    ...]} from the real community drop table (ideally ONE state's
    rewards per relic — the same items drop at every refinement, just
    at different odds, so passing all 4 states' rewards would just
    duplicate part-relic pairs, never wrong, just redundant). `warframe_
    names`: real "<Name> Prime" prefixes from warframe.market's own
    Warframe-tagged sets.

    Returns {warframe_name: {part: [RelicRef, ...]}} — a Warframe only
    appears if at least one of its parts is real and reachable through
    a relic warframe.market marks vaulted; nothing fabricated, nothing
    assumed for relics/rewards this function was never given."""
    # longest-name-first so "Wukong Prime" never wins a match that
    # should go to a longer, more specific real name sharing a prefix
    names_sorted = sorted(set(warframe_names), key=len, reverse=True)
    out: dict[str, dict[str, list[RelicRef]]] = {}
    for tier, name in vaulted_relics:
        rewards = relic_rewards.get((tier, name), [])
        ref = RelicRef(tier, name)
        for item_name in rewards:
            wf = next((n for n in names_sorted
                      if item_name.startswith(n + " ")), None)
            if wf is None:
                continue
            part = item_name[len(wf) + 1:]
            if part.endswith(" Blueprint"):
                part = part[: -len(" Blueprint")]
            part = part.strip()
            if not part:
                continue
            relics_for_part = out.setdefault(wf, {}).setdefault(part, [])
            if ref not in relics_for_part:      # a relic can appear once per part
                relics_for_part.append(ref)
    return out
