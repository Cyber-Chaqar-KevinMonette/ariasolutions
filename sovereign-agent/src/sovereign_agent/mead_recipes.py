"""mead_recipes.py — 🍯 curated, grounded mead recipes (Kevin's ask).

"People can get good recipes from Aria." These are REAL, classic,
community-trusted recipes written out here (not model-generated), so she
never hallucinates a batch. `/mead-recipe [style]` returns one; a bare
call lists the styles. Ingredient deals come from the 🍯 mead-brewing
tracker. 21+ content — surfaced only in the age-gated Mead Lounge.
"""
from __future__ import annotations

from dataclasses import dataclass


# the flavor vocabulary the taste-profiler + suggester speak
FLAVORS = ("sweet", "dry", "semi-sweet", "fruity", "spiced", "strong",
           "session", "clean", "complex", "traditional")


@dataclass(frozen=True)
class Recipe:
    slug: str
    name: str
    abv: str
    difficulty: str
    body: str
    flavors: tuple[str, ...] = ()   # taste tags for the suggestion engine


RECIPES: list[Recipe] = [
    Recipe(
        "jaom", "Joe's Ancient Orange Mead (JAOM)", "~12-14%", "beginner",
        "🍯 **Joe's Ancient Orange Mead** — the classic no-equipment "
        "starter.\n"
        "**For a 1-gallon jug:**\n"
        "• 3.5 lb (1.6 kg) honey\n"
        "• 1 large orange, quartered (peel on)\n"
        "• 1 small handful raisins (~25)\n"
        "• 1 stick cinnamon · 1 whole clove · optional pinch nutmeg\n"
        "• 1 tsp bread yeast (yes, really — traditional)\n"
        "• Water to fill\n"
        "**Steps:** Dissolve honey in warm (not hot) water. Add to the jug "
        "with the orange, raisins, spices. Top with water leaving headspace. "
        "Sprinkle the yeast on top (no stirring). Fit an airlock. Ferment at "
        "room temp ~2 months until the fruit sinks and it clears. Rack off "
        "the fruit, bottle, and age — it's better after 3-6 months.\n"
        "Forgiving, sweet, and nearly foolproof.",
        flavors=("sweet", "spiced", "fruity", "strong")),
    Recipe(
        "traditional", "Traditional Dry Mead", "~12-14%", "intermediate",
        "🍯 **Traditional Dry Mead** — clean, honey-forward.\n"
        "**For 1 gallon:**\n"
        "• 3 lb (1.36 kg) honey\n"
        "• 1 tsp yeast nutrient (staggered: 1/3 now, 1/3 day 2, 1/3 day 4)\n"
        "• Wine yeast (Lalvin 71B for a rounder mead, or EC-1118 for dry/"
        "clean)\n"
        "• Water to 1 gallon\n"
        "**Steps:** Mix honey + water (the 'must') to ~1.100 OG. Pitch "
        "rehydrated yeast at room temp. Stagger the nutrient + degas daily "
        "the first week. Ferment ~2-4 weeks to dry, rack to secondary, clear "
        "1-2 months, bottle, age 6+ months. Patience is the ingredient most "
        "people skip.",
        flavors=("dry", "clean", "strong", "traditional")),
    Recipe(
        "melomel", "Berry Melomel (fruit mead)", "~12%", "intermediate",
        "🍯 **Berry Melomel** — mead + fruit.\n"
        "**For 1 gallon:**\n"
        "• 2.5-3 lb honey\n"
        "• 2-3 lb fresh or frozen berries (blackberry, raspberry, "
        "blueberry)\n"
        "• 1 tsp nutrient (staggered) · wine yeast (71B or D47)\n"
        "**Steps:** Ferment the honey must first; add sanitized fruit in "
        "secondary (freezing then thawing the fruit breaks it down). Rack off "
        "the fruit after 1-2 weeks, clear, bottle, age. Add fruit in "
        "secondary — boiling it sets pectin and dulls the aroma.",
        flavors=("fruity", "semi-sweet", "strong", "complex")),
    Recipe(
        "session", "Quick Session Mead (short mead)", "~5-7%", "beginner",
        "🍯 **Session Mead** — light, drinkable in weeks.\n"
        "**For 1 gallon:**\n"
        "• 1.5-2 lb honey (lower = lighter, faster)\n"
        "• 1 tsp nutrient · a clean ale or wine yeast\n"
        "**Steps:** Same as traditional but with less honey → lower ABV and "
        "a much shorter age. Drinkable in 3-6 weeks. Great first batch to "
        "learn the process without a long wait.",
        flavors=("session", "semi-sweet", "clean")),
]

_BY_SLUG = {r.slug: r for r in RECIPES}
# friendly aliases
_ALIASES = {"orange": "jaom", "ancient": "jaom", "dry": "traditional",
            "classic": "jaom", "fruit": "melomel", "berry": "melomel",
            "quick": "session", "short": "session", "beginner": "jaom"}


def get_recipe(style: str = "") -> Recipe | None:
    s = (style or "").strip().lower()
    if not s:
        return None
    if s in _BY_SLUG:
        return _BY_SLUG[s]
    if s in _ALIASES:
        return _BY_SLUG[_ALIASES[s]]
    for r in RECIPES:                  # loose contains match
        if s in r.name.lower() or s in r.slug:
            return r
    return None


def list_styles() -> str:
    lines = ["🍯 **Mead recipes** — pick a style with `/mead-recipe <style>`:",
             ""]
    for r in RECIPES:
        lines.append(f"• **{r.slug}** — {r.name} ({r.abv}, {r.difficulty})")
    lines.append("")
    lines.append("New to mead? Start with **jaom** (Joe's Ancient Orange) — "
                 "no special gear, nearly foolproof. 🍯")
    return "\n".join(lines)


def render_recipe(style: str = "") -> str:
    r = get_recipe(style)
    if r is None:
        return list_styles()
    return (r.body + f"\n\n_{r.abv} ABV · {r.difficulty} · always brew + "
            "drink responsibly, 21+_ 🍯")


__all__ = ["FLAVORS", "Recipe", "RECIPES", "get_recipe", "list_styles",
           "render_recipe"]
