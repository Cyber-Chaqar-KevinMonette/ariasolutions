"""Tests for mead_recipes — curated, grounded (never model-generated)."""
from __future__ import annotations

from sovereign_agent.mead_recipes import (
    RECIPES,
    get_recipe,
    list_styles,
    render_recipe,
)


def test_recipes_are_real_and_complete():
    assert len(RECIPES) >= 4
    for r in RECIPES:
        assert r.name and r.abv and r.difficulty
        assert "honey" in r.body.lower()          # it's actually mead
        assert len(r.body) > 200                  # a real recipe, not a stub


def test_lookup_by_slug_and_alias():
    assert get_recipe("jaom").slug == "jaom"
    assert get_recipe("orange").slug == "jaom"    # alias
    assert get_recipe("berry").slug == "melomel"  # alias
    assert get_recipe("dry").slug == "traditional"
    assert get_recipe("nonsense") is None


def test_render_lists_when_blank_and_shows_recipe():
    out = list_styles()
    assert "jaom" in out and "mead-recipe" in out
    r = render_recipe("jaom")
    assert "Joe's Ancient Orange" in r and "airlock" in r.lower()
    assert "21+" in r                             # responsible-drinking note
    # blank → the style list, never a made-up recipe
    assert "pick a style" in render_recipe("").lower()
