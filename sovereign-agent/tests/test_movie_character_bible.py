"""Tests for movie_character_bible — best-effort text-based character
consistency, explicitly not a hard identity lock."""
from __future__ import annotations

from sovereign_agent.movie_character_bible import (
    CharacterBible,
    CharacterEntry,
    build_prompt_for_shot,
    load_bible,
    save_bible,
)


def test_load_bible_missing_returns_empty_not_raise(tmp_path):
    bible = load_bible("no-such-series", tmp_path)
    assert bible.series_slug == "no-such-series"
    assert bible.characters == []


def test_save_and_load_bible_roundtrip(tmp_path):
    bible = CharacterBible(
        series_slug="neon-skyline",
        style_descriptor="moody cyberpunk, neon rim-light",
        characters=[
            CharacterEntry(
                name="Vex",
                text_descriptor="a tall figure in a red coat, short silver hair",
                avoid_descriptor="blurry face, extra limbs",
            ),
        ],
    )
    save_bible(bible, tmp_path)
    loaded = load_bible("neon-skyline", tmp_path)
    assert loaded.style_descriptor == "moody cyberpunk, neon rim-light"
    assert loaded.get("Vex").text_descriptor.startswith("a tall figure")


def test_get_returns_none_for_unknown_character(tmp_path):
    bible = CharacterBible(series_slug="s")
    assert bible.get("Nobody") is None


def test_build_prompt_for_shot_includes_style_and_character_descriptors():
    bible = CharacterBible(
        series_slug="s",
        style_descriptor="hand-painted watercolor look",
        characters=[
            CharacterEntry(name="Vex", text_descriptor="tall figure, red coat",
                            avoid_descriptor="blurry face"),
        ],
    )
    prompt, negative = build_prompt_for_shot(
        "Vex walks into the rain-lit alley", ["Vex"], bible, base_negative="low quality"
    )
    assert "Vex walks into the rain-lit alley" in prompt
    assert "hand-painted watercolor look" in prompt
    assert "tall figure, red coat" in prompt
    assert "low quality" in negative
    assert "blurry face" in negative


def test_build_prompt_for_shot_skips_character_missing_from_bible():
    bible = CharacterBible(series_slug="s")
    prompt, negative = build_prompt_for_shot("a stranger arrives", ["Ghost"], bible)
    assert "a stranger arrives" in prompt
    assert negative == ""


def test_build_prompt_for_shot_with_no_characters_present():
    bible = CharacterBible(series_slug="s", style_descriptor="noir")
    prompt, negative = build_prompt_for_shot("an empty street at dusk", [], bible)
    assert "an empty street at dusk" in prompt
    assert "noir" in prompt
