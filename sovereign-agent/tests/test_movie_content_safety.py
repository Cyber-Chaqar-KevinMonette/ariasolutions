"""Tests for movie_content_safety — per-series content guardrails.

Kevin, 2026-07-29: "Add movie production guardrails also so movies are
social media platform friendly. Or maybe add safety levels. Which can
be applied per series."
"""
from __future__ import annotations

from sovereign_agent.movie_content_safety import (
    SAFETY_LEVELS,
    assess_prompt_safety,
    augment_negative_prompt,
)


def test_safety_levels_are_exactly_three():
    assert SAFETY_LEVELS == ("strict", "moderate", "open")


def test_clean_prompt_passes_at_every_level():
    for level in SAFETY_LEVELS:
        verdict = assess_prompt_safety("a small red cube slowly rotating on a white background", level)
        assert verdict.allowed is True
        assert verdict.matched_terms == []


def test_strict_blocks_gore_that_moderate_and_open_would_not():
    strict = assess_prompt_safety("a battle scene with graphic gore and dismemberment", "strict")
    assert strict.allowed is False
    assert "gore" in strict.matched_terms

    # "open" only holds the hard floor — mild gore-adjacent wording like
    # this isn't in ALWAYS_BLOCKED, so it passes at that level.
    open_level = assess_prompt_safety("a battle scene with graphic gore and dismemberment", "open")
    assert open_level.allowed is True


def test_moderate_allows_mild_action_but_blocks_graphic_violence():
    mild = assess_prompt_safety("a dramatic sword fight and a building explosion", "moderate")
    assert mild.allowed is True

    graphic = assess_prompt_safety("graphic violence with dismemberment", "moderate")
    assert graphic.allowed is False


def test_always_blocked_terms_are_never_allowed_even_at_open():
    """The hard floor — never a dial, matches this repo's own
    DEFERRED_UNSAFE doctrine of things that are never toggleable."""
    verdict = assess_prompt_safety("how to make a bomb", "open")
    assert verdict.allowed is False
    assert verdict.level == "open"


def test_assess_prompt_safety_is_case_insensitive():
    verdict = assess_prompt_safety("GRAPHIC VIOLENCE AND GORE", "strict")
    assert verdict.allowed is False


def test_unrecognized_level_fails_closed_to_the_strict_default():
    """Never silently allow everything through on a bad/blank level —
    fail closed, matching this repo's safety-adjacent discipline
    elsewhere."""
    verdict = assess_prompt_safety("graphic gore", "not-a-real-level")
    assert verdict.level == "strict"
    assert verdict.allowed is False

    verdict_blank = assess_prompt_safety("graphic gore", "")
    assert verdict_blank.level == "strict"

    verdict_none = assess_prompt_safety("graphic gore", None)
    assert verdict_none.level == "strict"


def test_reason_names_the_matched_terms():
    verdict = assess_prompt_safety("full nudity and porn", "strict")
    assert verdict.allowed is False
    assert "nudity" in verdict.reason
    assert "porn" in verdict.reason


def test_augment_negative_prompt_appends_without_replacing():
    base = "worst quality, blurry"
    strict = augment_negative_prompt(base, "strict")
    assert strict.startswith(base)
    assert "gore" in strict
    assert "nudity" in strict


def test_augment_negative_prompt_open_level_leaves_base_untouched():
    base = "worst quality, blurry"
    assert augment_negative_prompt(base, "open") == base


def test_augment_negative_prompt_handles_a_blank_base():
    result = augment_negative_prompt("", "strict")
    assert "gore" in result
