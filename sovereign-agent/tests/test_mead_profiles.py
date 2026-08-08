"""Tests for mead_profiles — the taste-profile mixologist."""
from __future__ import annotations

from sovereign_agent.mead_profiles import (
    compose_palate,
    load_profile,
    parse_idea,
    rate_recipe,
    render_suggestions,
    set_taste,
    suggest,
)


def test_first_timer_gets_a_diverse_flight(tmp_path):
    # no profile → a spread, never empty, never a fabricated recipe
    sugg = suggest(tmp_path, "55")
    assert len(sugg) == 3
    assert sugg[0]["source"] == "flight"
    slugs = {s["slug"] for s in sugg}
    assert len(slugs) == 3                         # diverse, not repeats


def test_idea_stems_suggestions(tmp_path):
    sugg = suggest(tmp_path, idea="something fruity and strong")
    assert sugg[0]["source"] == "your idea"
    top = sugg[0]
    # a fruity+strong recipe should surface (melomel or jaom)
    assert top["slug"] in ("melomel", "jaom")
    assert "fruity" in top["why"] or "strong" in top["why"]


def test_parse_idea_only_real_flavors():
    tags = parse_idea("I want something dry and clean, not too sweet")
    assert "dry" in tags and "clean" in tags
    assert parse_idea("boozy berry") == ["fruity", "strong"] or \
        set(parse_idea("boozy berry")) == {"fruity", "strong"}
    assert parse_idea("purple monkey dishwasher") == []


def test_palate_learns_from_taste_and_ratings(tmp_path):
    set_taste(tmp_path, "7", likes=["sweet", "spiced"], dislikes=["dry"])
    p = load_profile(tmp_path, "7")
    assert "sweet" in p["likes"] and "dry" in p["dislikes"]
    # a 5-star rating pulls the recipe's flavors into likes
    rate_recipe(tmp_path, "7", "melomel", 5)
    p = load_profile(tmp_path, "7")
    assert "fruity" in p["likes"]                  # melomel is fruity
    assert p["ratings"]["melomel"] == 5
    # suggestions now tuned to the profile
    sugg = suggest(tmp_path, "7")
    assert sugg[0]["source"] == "your taste profile"
    assert any("sweet" in s["why"] or "fruity" in s["why"] for s in sugg)


def test_low_rating_pushes_to_dislikes(tmp_path):
    rate_recipe(tmp_path, "9", "traditional", 1)   # dry/clean/strong
    p = load_profile(tmp_path, "9")
    assert "dry" in p["dislikes"] or "clean" in p["dislikes"]


def test_render_and_palate_text(tmp_path):
    assert "flight" in render_suggestions(tmp_path, "1").lower() or \
        "palate" in render_suggestions(tmp_path, "1").lower()
    assert "don't know your palate" in compose_palate(tmp_path, "1")
    set_taste(tmp_path, "1", likes=["fruity"])
    out = render_suggestions(tmp_path, "1")
    assert "/mead-recipe" in out and "/mead-rate" in out
    assert "loves: fruity" in compose_palate(tmp_path, "1")
