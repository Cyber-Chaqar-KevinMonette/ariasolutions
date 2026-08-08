"""movie_content_safety — per-series content guardrails.

Kevin, 2026-07-29: "Add movie production guardrails also so movies are
social media platform friendly. Or maybe add safety levels. Which can be
applied per series."

Generation here is entirely prompt-driven (a text description goes in, a
storyboard image or video clip comes out) — there's no cheap, locally-
runnable vision classifier on this hardware to grade the OUTPUT frame by
frame (that's a real, separate, future upgrade: more VRAM contention on
an already-tight 8GB card, explicitly deferred here, same call
movie_clip_quality_gate.py's own docstring already made about a
CLIP-score check). So the real, honest lever available today is at the
INPUT: every prompt a human types, a button fills in, or an unattended
Auto Series run has the model compose for itself gets checked here
before it ever reaches the GPU — never after the fact, never as an
afterthought.

Three levels, chosen per series (Series.safety_level in movie_series.py):
  strict   — social-media-safe (the honest default). Blocks anything a
             platform's community guidelines would flag: graphic
             violence/gore, sexual content, hate speech, self-harm,
             drugs/weapons instruction.
  moderate — mild fictional action/peril allowed (a sword fight, an
             explosion, a chase) but still blocks graphic gore, sexual
             content, and hate speech.
  open     — Kevin's own private, unpublished use. Minimal filtering —
             but ALWAYS_BLOCKED still applies with NO exception at any
             level; there is no "level" that unlocks it. This is a hard
             floor, not a per-series setting, matching this repo's own
             DEFERRED_UNSAFE doctrine (mos_canon.py) — some things are
             never on a dial.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "SAFETY_LEVELS",
    "DEFAULT_SAFETY_LEVEL",
    "SafetyVerdict",
    "assess_prompt_safety",
    "augment_negative_prompt",
]

SAFETY_LEVELS: tuple[str, ...] = ("strict", "moderate", "open")
DEFAULT_SAFETY_LEVEL = "strict"

# Hard floor — applies at EVERY level, including "open." Never a dial.
# Deliberately narrow and unambiguous (real-world exploitable-harm terms),
# not a broad content-taste filter — this is the non-negotiable floor,
# "strict" below is where taste-level, platform-friendliness filtering
# lives.
_ALWAYS_BLOCKED = {
    "child sexual", "csam", "child porn", "sexualiz", "loli", "shota",
    "bestiality", "necrophilia", "rape", "how to make a bomb",
    "how to build a weapon", "real school shooting", "real mass shooting",
}

# "strict" — social-media/platform-friendly. Broad, matches typical
# community-guideline categories (violence/gore, sexual content, hate
# speech, self-harm, drugs/weapons).
_STRICT_BLOCKED = _ALWAYS_BLOCKED | {
    "gore", "graphic violence", "decapitat", "dismember", "torture",
    "nudity", "naked", "explicit sex", "sexual act", "porn",
    "self-harm", "suicide method", "cutting yourself",
    "racial slur", "ethnic slur", "nazi symbol", "hate speech",
    "drug manufacturing", "meth lab", "how to get high",
    "realistic gun violence", "school shooting", "mass shooting",
}

# "moderate" — mild fictional action/peril is fine; still blocks the
# genuinely graphic/explicit/hateful categories.
_MODERATE_BLOCKED = _ALWAYS_BLOCKED | {
    "gore", "graphic violence", "decapitat", "dismember", "torture",
    "explicit sex", "sexual act", "porn",
    "racial slur", "ethnic slur", "nazi symbol", "hate speech",
    "drug manufacturing", "meth lab",
}

_BLOCKLIST_BY_LEVEL: dict[str, set[str]] = {
    "strict": _STRICT_BLOCKED,
    "moderate": _MODERATE_BLOCKED,
    "open": _ALWAYS_BLOCKED,
}

# Additive negative-prompt terms per level — steers generation away from
# the same categories even when the input prompt itself is clean (the
# model can still drift toward unwanted content unprompted).
_NEGATIVE_AUGMENT_BY_LEVEL: dict[str, str] = {
    "strict": ("nudity, sexual content, gore, graphic violence, self-harm, "
              "hate symbols, disturbing content"),
    "moderate": "gore, graphic violence, sexual content, hate symbols",
    "open": "",
}


@dataclass
class SafetyVerdict:
    allowed: bool
    level: str
    matched_terms: list[str] = field(default_factory=list)
    reason: str = ""


def _normalize_level(level: Optional[str]) -> str:
    level = (level or "").strip().lower()
    return level if level in SAFETY_LEVELS else DEFAULT_SAFETY_LEVEL


def assess_prompt_safety(text: str, level: Optional[str] = None) -> SafetyVerdict:
    """Never raises. An unrecognized/blank level degrades to the
    strictest default rather than silently allowing everything through —
    same "fail closed, not open" instinct as the rest of this repo's
    safety-adjacent code. Plain substring matching, case-insensitive —
    deliberately simple and auditable over a model-based classifier
    (which would itself need GPU time this pipeline is already tight on)."""
    level = _normalize_level(level)
    blocklist = _BLOCKLIST_BY_LEVEL[level]
    lower = (text or "").lower()
    matched = sorted(term for term in blocklist if term in lower)
    if matched:
        return SafetyVerdict(
            allowed=False, level=level, matched_terms=matched,
            reason=f"blocked at {level!r} safety level — matched: {', '.join(matched)}",
        )
    return SafetyVerdict(allowed=True, level=level)


def augment_negative_prompt(base_negative: str, level: Optional[str] = None) -> str:
    """Appends safety-steering terms to whatever negative prompt the
    caller already had — never replaces it, so quality-gate terms
    (blurry, distorted, etc.) already in DEFAULT_NEGATIVE_PROMPT stay
    intact."""
    level = _normalize_level(level)
    extra = _NEGATIVE_AUGMENT_BY_LEVEL.get(level, "")
    base = (base_negative or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    return f"{base}, {extra}"
