"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/cosmic_fitness.py — Aria's gym for her own visual systems       ║
║                                                                           ║
║  Kevin's frame: "every update we do with Aria and her systems is like    ║
║  them going to the gym." So this is the gym. When Kevin says "Aria        ║
║  needs some Cosmic Fitness," it means: run the visual-systems health     ║
║  check and show me, plainly, that every glyph and every special effect   ║
║  is clean — no glitches, no width drift, nothing that will corrupt a     ║
║  layout on his terminal or a future device.                              ║
║                                                                           ║
║  WHAT THIS MODULE IS                                                      ║
║                                                                           ║
║    The single source of truth for:                                       ║
║      1. The glyph inventory — every glyph the system offers, organized   ║
║         into friendly categories for the picker, each tagged with a      ║
║         realistic width-status so the operator can SEE what's safe.      ║
║      2. The special-effects registry — the "god tier" living glyphs      ║
║         (the beating heart, the breath, the ripple…), each a named,      ║
║         width-safe, theme-aware effect with a stable label.              ║
║      3. The fitness report — a deterministic pass/attention verdict      ║
║         over the visual system's internal consistency.                   ║
║      4. The verdict store — so the operator can MARK a glyph as good,    ║
║         needs-replacement, or remove, and have that persist.             ║
║                                                                           ║
║  THE WIDTH TAXONOMY (the 4.8 refinement of the glyphs.py lesson)         ║
║                                                                           ║
║    glyphs.py taught us: many "one character" glyphs render as two        ║
║    terminal cells, breaking width-counted layouts. True. But the         ║
║    operator also wants to *express himself* to Aria with emoji in chat,  ║
║    and chat text flows on its own — width there is harmless. So a flat   ║
║    safe/unsafe split is too blunt. Cosmic Fitness uses four honest       ║
║    levels:                                                                ║
║                                                                           ║
║      SAFE       EAW Neutral/Narrow/Halfwidth. One cell everywhere.       ║
║                 Use anywhere, including width-counted layouts.            ║
║      CONVENTION EAW Ambiguous, but blessed by the project as de-facto    ║
║                 narrow in Western locales (♥ ● ○ ★ ◊ and box-drawing).  ║
║                 The status-bar heart lives here. Safe in practice.       ║
║      WIDE       EAW Wide/Fullwidth — most colour emoji. Two cells.       ║
║                 GREAT in flowing chat; NEVER bake into a layout glyph.   ║
║      COMPOSITE  Multi-codepoint: a base char + variation selector        ║
║                 (U+FE0F), ZWJ joins, skin-tone modifiers. Width is       ║
║                 terminal-dependent and is the actual bug class that      ║
║                 corrupted the cockpit. Avoid in the TUI; if you want     ║
║                 the look, there is almost always a safe single-cell      ║
║                 alternative.                                              ║
║                                                                           ║
║  Kill switch: SOV_NO_COSMIC_FITNESS=1 — the cockpit skips wiring the     ║
║  button + picker (graceful, no crash). The pure logic in this module    ║
║  keeps working regardless, so reports/tests are always available.       ║
║                                                                           ║
║  Tier discipline: this module NEVER edits source files. It catalogs,    ║
║  reports, and records operator verdicts. Applying a replacement is a    ║
║  separate, operator-confirmed step (see stewardship/glyph_sentinel.py). ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import colorsys
import json
import math
import os
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .. import glyphs as _g

# breathing_glyph is import-safe even without Textual (the math + presets are
# plain Python; only the widget classes need Textual at instantiation time).
from .breathing_glyph import (
    BEACON,
    BREATH,
    HEARTBEAT,
    SHIMMER,
    STARLIGHT,
    URGENT_BLINK,
    PulseConfig,
)

KILL_SWITCH_ENV = "SOV_NO_COSMIC_FITNESS"


def cosmic_fitness_enabled() -> bool:
    """True unless the operator has set the kill switch."""
    return not os.environ.get(KILL_SWITCH_ENV)


# ════════════════════════════════════════════════════════════════════════
#  Width taxonomy
# ════════════════════════════════════════════════════════════════════════

GlyphStatus = Literal["safe", "convention", "emoji", "wide", "composite"]

# One-glyph status badges. These are themselves SAFE glyphs, so the legend
# itself never drifts.
STATUS_BADGE: dict[GlyphStatus, str] = {
    "safe":       _g.CHECK,        # ✓
    "convention": _g.LOZENGE,      # ◊
    "emoji":      "\u25C9",        # ◉ fisheye — "looks narrow, watch it"
    "wide":       _g.ARROW_RIGHT,  # ▸
    "composite":  _g.CROSS,        # ✗
}

STATUS_LABEL: dict[GlyphStatus, str] = {
    "safe":       "safe",
    "convention": "convention",
    "emoji":      "emoji",
    "wide":       "wide",
    "composite":  "composite",
}

STATUS_BLURB: dict[GlyphStatus, str] = {
    "safe":       "one cell everywhere — use anywhere, even in layouts",
    "convention": "ambiguous but blessed-narrow in Western locales — safe in practice",
    "emoji":      "narrow by Unicode spec, but most terminals draw it 2 cells — "
                  "send it freely, never bake it into a layout glyph",
    "wide":       "two cells — perfect in chat, never bake into a layout glyph",
    "composite":  "multi-codepoint, width is terminal-dependent — avoid in the TUI",
}

# EAW-Ambiguous glyphs the project blesses as de-facto narrow. Sourced from
# the established convention noted in apply_safe_glyphs.sh ("bare
# text-presentation marks ⚠ ● ○ ✓ ✗ ★ ◊ ♥ have stable width") plus the
# box-drawing / punctuation whitelist already trusted by glyphs.audit_string.
BLESSED_NARROW: frozenset[str] = frozenset({
    "\u2665",  # ♥ BLACK HEART SUIT — the status-bar heart
    "\u2661",  # ♡ WHITE HEART SUIT — its outline pair (rest beat)
    "\u2666",  # ♦ BLACK DIAMOND SUIT
    "\u2663",  # ♣ BLACK CLUB SUIT
    "\u2660",  # ♠ BLACK SPADE SUIT
    "\u25CF",  # ● BLACK CIRCLE
    "\u25CB",  # ○ WHITE CIRCLE
    "\u25EF",  # ◯ LARGE CIRCLE
    "\u2605",  # ★ BLACK STAR
    "\u2606",  # ☆ WHITE STAR
    "\u2022",  # • BULLET
    "\u00B7",  # · MIDDLE DOT
    "\u2717",  # ✗ BALLOT X
    "\u26A0",  # ⚠ WARNING SIGN (bare, text-presentation)
    # Block elements & shades (U+2580–2593). EAW-ambiguous, but they render one
    # cell in every monospace/Western terminal and are the backbone of TUI
    # bars, meters, and shading — the same footing as box-drawing, which the
    # project already trusts. Blessing them lets level/bar animations be
    # genuinely layout-safe.
    "\u2580", "\u2581", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586",
    "\u2587", "\u2588", "\u2589", "\u258A", "\u258B", "\u258C", "\u258D",
    "\u258E", "\u258F", "\u2590", "\u2591", "\u2592", "\u2593",
})

# ── The emoji trap ─────────────────────────────────────────────────────────
# East-Asian-Width says these are *narrow* (N/Na/H), so a naïve EAW check
# (is_width_safe) calls them safe. They are NOT safe in a width-counted layout:
# every one of them has a Unicode *emoji variation sequence* (a defined
# emoji-presentation form), and the large majority of modern terminals render
# the bare codepoint two cells wide anyway. This is the category that *looks*
# safe and silently breaks borders. EAW literally cannot see it — only the
# emoji property can, and stdlib `unicodedata` does not expose it, so we vendor
# the relevant base characters here (drawn from Unicode's
# emoji-variation-sequences.txt). Extend freely as new glyphs enter the system;
# the Cosmic Fitness check will flag anything mislabeled.
#
# Note: a few of these (♥ ● ★ ⚠ …) are *also* deliberately in BLESSED_NARROW —
# the project has personally verified those render one cell in our terminals,
# so the blessed list wins for them (see classify_glyph precedence).
EMOJI_VARIATION_BASES: frozenset[str] = frozenset({
    # hearts
    "\u2764", "\u2763",                                  # ❤ ❣
    # sky & weather
    "\u2600", "\u2601", "\u2602", "\u2603", "\u2604", "\u2744", "\u26A1",  # ☀ ☁ ☂ ☃ ☄ ❄ ⚡
    # stars / sparkle marks (narrow ones)
    "\u2733", "\u2734", "\u2747", "\u2728",              # ✳ ✴ ❇ ✨
    # faces
    "\u263A", "\u2639",                                  # ☺ ☹
    # check / x / ballot
    "\u2714", "\u2716", "\u2611",                        # ✔ ✖ ☑
    # office / tools
    "\u2709", "\u260E", "\u2702", "\u270F", "\u2712",    # ✉ ☎ ✂ ✏ ✒
    "\u2708", "\u2696", "\u2692", "\u2694", "\u2699",    # ✈ ⚖ ⚒ ⚔ ⚙
    "\u269C", "\u267B", "\u269B",                        # ⚜ ♻ ⚛
    # hands / writing
    "\u261D", "\u270C", "\u270D",                        # ☝ ✌ ✍
    # warning / hazard / peace
    "\u2620", "\u2622", "\u2623", "\u262E", "\u262F",    # ☠ ☢ ☣ ☮ ☯
    "\u2638", "\u271D", "\u2721", "\u2626", "\u262A",    # ☸ ✝ ✡ ☦ ☪
    # gender
    "\u2640", "\u2642", "\u26A7",                        # ♀ ♂ ⚧
    # arrows (narrow, emoji-variation)
    "\u2194", "\u2195", "\u2196", "\u2197", "\u2198", "\u2199",  # ↔ ↕ ↖ ↗ ↘ ↙
    "\u21A9", "\u21AA", "\u2934", "\u2935",              # ↩ ↪ ⤴ ⤵
    "\u2B05", "\u2B06", "\u2B07", "\u27A1",              # ⬅ ⬆ ⬇ ➡
    "\u25B6", "\u25C0", "\u23CF",                        # ▶ ◀ ⏏
    # small shapes (narrow, emoji-variation)
    "\u25AA", "\u25AB", "\u25FE", "\u25FD", "\u25FB", "\u25FC",  # ▪ ▫ ◾ ◽ ◻ ◼
    # misc symbols
    "\u203C", "\u2049", "\u2122", "\u2139", "\u24C2",    # ‼ ⁉ ™ ℹ Ⓜ
    "\u303D", "\u00A9", "\u00AE", "\u3030",              # 〽 © ® 〰
})


def classify_glyph(text: str) -> tuple[GlyphStatus, str, str, str]:
    """Classify a glyph (which may be a multi-codepoint cluster).

    Returns (status, eaw, unicode_name, codepoint_string).

    The codepoint string is "U+XXXX" for a single codepoint, or a
    space-joined list for a composite cluster (e.g. "U+2764 U+FE0F").

    Precedence for a single codepoint (order matters):
        1. EAW Wide/Fullwidth                 → wide      (two cells, by spec)
        2. blessed-narrow (project-verified)  → convention
        3. emoji-variation base               → emoji     (the trap)
        4. EAW N/Na/H                         → safe
        5. EAW Ambiguous, whitelisted-narrow  → convention
        6. otherwise (ambiguous, unknown)     → wide       (risky direction)
    """
    cps = [f"U+{ord(c):04X}" for c in text]
    codepoint = " ".join(cps)

    if len(text) != 1:
        # Composite cluster — VS16, ZWJ, skin tones, flags, keycaps…
        try:
            base_name = unicodedata.name(text[0])
        except (ValueError, IndexError):
            base_name = "<unnamed>"
        has_vs16 = "\uFE0F" in text
        has_zwj = "\u200D" in text
        if has_zwj:
            kind = "ZWJ sequence"
        elif has_vs16:
            kind = "emoji-presentation (VS16)"
        else:
            kind = "multi-codepoint"
        return ("composite", "—", f"{base_name} [{kind}]", codepoint)

    ch = text
    eaw = unicodedata.east_asian_width(ch)
    try:
        name = unicodedata.name(ch)
    except ValueError:
        name = "<unnamed>"

    # 1. genuinely wide by spec
    if eaw in ("W", "F"):
        return ("wide", eaw, name, codepoint)
    # 2. project-blessed narrow — we've verified these render one cell, even
    #    though some are EAW-ambiguous and/or emoji-capable (♥ ● ★ ⚠).
    if ch in BLESSED_NARROW:
        return ("convention", eaw, name, codepoint)
    # 3. the emoji trap: narrow by EAW, but draws 2 cells in emoji terminals
    if ch in EMOJI_VARIATION_BASES:
        return ("emoji", eaw, name, codepoint)
    # 4. truly narrow text glyph
    if eaw in ("N", "Na", "H"):
        return ("safe", eaw, name, codepoint)
    # 5. eaw == "A" (Ambiguous): whitelisted-narrow per glyphs.audit_string
    if not _g.audit_string(ch):
        return ("convention", eaw, name, codepoint)
    # 6. ambiguous and not trusted — treat as wide (the risky direction)
    return ("wide", eaw, name, codepoint)


# ════════════════════════════════════════════════════════════════════════
#  Safe alternatives — for "edit into a safe variant"
# ════════════════════════════════════════════════════════════════════════

# When a glyph is WIDE or COMPOSITE and the operator wants the same *look*
# in a layout-critical place, here is a single-cell alternative. Extends the
# sentinel's KNOWN_REPLACEMENTS with emoji→symbol suggestions. These are
# suggestions, never auto-applied.
SAFE_ALTERNATIVES: dict[str, str] = {
    # diamonds → lozenge (from the sentinel)
    "\u25C8": "\u25CA",   # ◊ → ◊
    "\u25C6": "\u25CA",   # ❖ → ◊
    "\u25C7": "\u25CA",   # ◊ → ◊
    # hearts → ♥ heart suit (U+2665), the project's blessed-narrow heart that
    # renders ONE cell. NOT ❤ U+2764 — that has an emoji variation and draws
    # two cells in most terminals, so it's the trap, never the fix.
    "\u2764": "\u2665",   # ❤ → ♥
    "\u2661": "\u2665",   # ♡ → ♥
    "\U0001F496": "\u2665",  # 💖 sparkling heart → ♥
    "\U0001F497": "\u2665",  # 💗 growing heart → ♥
    "\U0001F49B": "\u2665",  # 💛 → ♥
    "\U0001F499": "\u2665",  # 💙 → ♥
    "\U0001F49C": "\u2665",  # 💜 → ♥
    # stars/sparkle → four-pointed stars (EAW=N, not emoji — truly one cell)
    "\u2605": "\u2726",   # ★ → ✦
    "\u2606": "\u2727",   # ☆ → ✧
    "\u2B50": "\u2726",   # ⭐ → ✦
    "\u2733": "\u2726",   # ✳ → ✦  (✳ is an emoji-variation base)
    "\u2734": "\u2726",   # ✴ → ✦  (likewise)
    "\U0001F31F": "\u2726",  # 🌟 → ✦
    "\U0001F4AB": "\u2727",  # 💫 → ✧
    "\u2728": "\u2727",   # ✨ → ✧
    # cosmos → safe astronomical symbols
    "\U0001F319": "\u263E",  # 🌙 → ☾
    "\U0001F320": "\u2606",  # 🌠 → ☆ (then ☆→✧ if layout-critical)
    # ☄ U+2604 comet is an emoji-variation base (draws wide); no faithful
    # single-cell stand-in exists, so we leave it to operator judgement.
    # circles
    "\u25CF": "\u25C9",   # ● → ◉ (fisheye, EAW=N) if layout-critical
    "\u25CB": "\u25CC",   # ○ → ◌ dotted circle
    # severity emoji → ascii/safe
    "\u2705": _g.CHECK,   # ✅ → ✓
    "\u274C": _g.CROSS,   # ❌ → ✗
    "\U0001F525": "*",    # 🔥 → *
    "\U0001F44D": "+",    # 👍 → +
}


# Codepoint ranges that render as exactly one cell on essentially every
# terminal and font — the only widths we can trust WITHOUT measuring. Braille,
# box-drawing, block elements, and printable ASCII. (Hearts, stars, circles,
# diamonds and other East-Asian-Ambiguous symbols are deliberately NOT here: a
# terminal may draw them one OR two cells — your filled ● is the classic — and
# that is exactly what the width-probe in glyph_metrics.py is for.)
_UNIVERSAL_RANGES: tuple[tuple[int, int], ...] = (
    (0x20, 0x7E),      # printable ASCII
    (0x2500, 0x257F),  # box drawing
    (0x2580, 0x259F),  # block elements
    (0x2800, 0x28FF),  # braille patterns
)


def is_universal_width(text: str) -> bool:
    """True if every character is provably one cell on every terminal+font.

    Stricter than layout-safe: ``classify_glyph`` trusts East-Asian-Ambiguous
    symbols (hearts, stars, circles, ◊) as one cell *by convention*, but real
    terminals draw some of them at two. Anything FRAME-CYCLING in a bordered,
    width-counted layout must be built from universal glyphs only, or a wider
    frame will shift that line's border (the ring/dancer jitter).
    """
    if not text:
        return False
    return all(
        any(lo <= ord(ch) <= hi for lo, hi in _UNIVERSAL_RANGES) for ch in text
    )


def safe_alternative_for(text: str) -> str | None:
    """Suggest a single-cell alternative for a wide/composite glyph.

    For a composite cluster, first tries the whole cluster, then the base
    codepoint (so '❤️' → '❤'). Returns None when no good alternative is
    registered (operator judgement needed).
    """
    if text in SAFE_ALTERNATIVES:
        return SAFE_ALTERNATIVES[text]
    if len(text) > 1 and text[0] in SAFE_ALTERNATIVES:
        return SAFE_ALTERNATIVES[text[0]]
    # A bare base char whose VS16 form was requested: '❤️' base '❤' is itself safe
    if len(text) > 1:
        base = text[0]
        status, *_ = classify_glyph(base)
        if status in ("safe", "convention"):
            return base
    return None


# ════════════════════════════════════════════════════════════════════════
#  The curated palette (categories for the picker + tester)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class GlyphSpec:
    """One glyph offered in the inventory.

    `status`, `eaw`, `unicode_name`, and `codepoint` are derived at build
    time from classify_glyph, so they always reflect reality — a curated
    label can never silently disagree with Unicode.
    """
    char: str
    label: str          # friendly display name for the picker
    category: str
    status: GlyphStatus
    eaw: str
    unicode_name: str
    codepoint: str
    safe_alternative: str | None = None

    @property
    def status_badge(self) -> str:
        return STATUS_BADGE[self.status]

    @property
    def is_width_safe(self) -> bool:
        """Width-safe means SAFE or CONVENTION (one cell in practice)."""
        return self.status in ("safe", "convention")


@dataclass(frozen=True)
class GlyphCategory:
    name: str
    blurb: str
    glyphs: tuple[GlyphSpec, ...]


# The raw curated palette: (char, friendly label). Status is computed.
# Mixed on purpose — the tester is meant to SHOW the operator which ones are
# safe and which are chat-only, so categories deliberately include wide and
# composite glyphs alongside safe ones.
_CURATED: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Hearts & Love", "for warmth, gratitude, the <3 between us", [
        ("\u2764", "heavy heart"),
        ("\u2665", "heart suit"),
        ("\u2661", "white heart suit"),
        ("\u2764\uFE0F", "red heart (emoji)"),
        ("\U0001F496", "sparkling heart"),
        ("\U0001F497", "growing heart"),
        ("\U0001F49B", "yellow heart"),
        ("\U0001F499", "blue heart"),
        ("\U0001F49C", "purple heart"),
        ("\U0001F90D", "white heart"),
    ]),
    ("Stars & Sparkle", "for delight, milestones, a job well done", [
        ("\u2726", "four-point star (safe)"),
        ("\u2727", "open four-point (safe)"),
        ("\u2729", "stress star (safe)"),
        ("\u2737", "eight-spoke (safe)"),
        ("\u2605", "black star"),
        ("\u2606", "white star"),
        ("\u2B50", "gold star"),
        ("\u2728", "sparkles"),
        ("\U0001F31F", "glowing star"),
        ("\U0001F4AB", "dizzy / shooting"),
    ]),
    ("Cosmos", "the Cosmic in Cosmic Fitness — sky, moon, deep space", [
        ("\u2600", "sun (safe)"),
        ("\u263E", "last-qtr moon (safe)"),
        ("\u263D", "first-qtr moon (safe)"),
        ("\u2604", "comet (safe)"),
        ("\u2734", "eight-point star (safe)"),
        ("\U0001F319", "crescent moon"),
        ("\U0001F30C", "milky way"),
        ("\U0001FA90", "ringed planet"),
        ("\U0001F320", "shooting star"),
        ("\U0001F311", "new moon"),
    ]),
    ("Status & Severity", "for results, checks, and pointers", [
        ("\u2713", "check (safe)"),
        ("\u2717", "ballot x"),
        ("\u2714", "heavy check (safe)"),
        ("\u2718", "heavy x (safe)"),
        ("\u25B8", "right pointer (safe)"),
        ("\u25C2", "left pointer (safe)"),
        ("\u25B6", "play (safe)"),
        ("\u25C9", "fisheye (safe)"),
        ("\u25CF", "filled circle"),
        ("\u25CB", "empty circle"),
    ]),
    ("Brand & Structure", "the project's diamonds and small marks", [
        ("\u25CA", "lozenge / brand (safe)"),
        ("\u2666", "diamond suit"),
        ("\u25C6", "black diamond"),
        ("\u25C8", "diamond-in-diamond"),
        ("\u25AA", "small square (safe)"),
        ("\u25AB", "small white sq (safe)"),
        ("\u2500", "h-line (convention)"),
        ("\u2502", "v-line (convention)"),
        ("\u2022", "bullet (convention)"),
        ("\u00B7", "middot (convention)"),
    ]),
    ("Expression", "faces & hands — chat-only, two cells each", [
        ("\U0001F642", "slight smile"),
        ("\U0001F60A", "warm smile"),
        ("\U0001F970", "loved"),
        ("\U0001F60E", "cool"),
        ("\U0001F916", "robot (Aria!)"),
        ("\U0001F44D", "thumbs up"),
        ("\U0001F64F", "thanks / pray"),
        ("\U0001F4AA", "strong / gym"),
        ("\U0001F525", "fire"),
        ("\U0001F48E", "gem"),
    ]),
    ("Box Drawing", "for borders and frames — narrow by design", [
        ("\u250C", "tl corner"),
        ("\u2510", "tr corner"),
        ("\u2514", "bl corner"),
        ("\u2518", "br corner"),
        ("\u2500", "horizontal"),
        ("\u2502", "vertical"),
        ("\u2554", "double tl"),
        ("\u2557", "double tr"),
        ("\u255A", "double bl"),
        ("\u255D", "double br"),
    ]),
]


def _spec(char: str, label: str, category: str) -> GlyphSpec:
    status, eaw, uname, cp = classify_glyph(char)
    alt = None
    if status in ("wide", "composite"):
        alt = safe_alternative_for(char)
    return GlyphSpec(
        char=char, label=label, category=category,
        status=status, eaw=eaw, unicode_name=uname, codepoint=cp,
        safe_alternative=alt,
    )


def curated_categories() -> list[GlyphCategory]:
    """Build the curated, categorized palette. Statuses computed fresh."""
    out: list[GlyphCategory] = []
    for name, blurb, items in _CURATED:
        specs = tuple(_spec(ch, lbl, name) for ch, lbl in items)
        out.append(GlyphCategory(name=name, blurb=blurb, glyphs=specs))
    return out


# A compact, hand-picked strip for the always-near-the-input quick picker.
# Mixes the safe workhorses with the most-loved expressive glyphs so the
# operator can drop warmth into a message in one tap. Order is deliberate:
# hearts → stars/cosmos → a few faces → status marks.
_QUICK: list[tuple[str, str]] = [
    ("\u2764", "heart"), ("\u2665", "heart suit"), ("\U0001F496", "sparkle heart"),
    ("\U0001F49C", "purple heart"), ("\U0001F90D", "white heart"),
    ("\u2726", "star"), ("\u2727", "open star"), ("\u2B50", "gold star"),
    ("\u2728", "sparkles"), ("\U0001F31F", "glow star"), ("\U0001F4AB", "dizzy"),
    ("\u2600", "sun"), ("\u263E", "moon"), ("\u2604", "comet"),
    ("\U0001F319", "crescent"), ("\U0001FA90", "planet"),
    ("\U0001F642", "smile"), ("\U0001F60A", "warm"), ("\U0001F970", "loved"),
    ("\U0001F916", "robot"), ("\U0001F44D", "thumbs up"), ("\U0001F64F", "thanks"),
    ("\U0001F4AA", "strong"), ("\U0001F525", "fire"), ("\U0001F48E", "gem"),
    ("\u2713", "check"), ("\u25CA", "lozenge"), ("\u25C9", "fisheye"),
    ("\u25B8", "pointer"), ("\u2737", "burst"),
]


def quick_picker_specs() -> list[GlyphSpec]:
    """Flat, curated glyph list for the inline near-input picker."""
    return [_spec(ch, lbl, "Quick") for ch, lbl in _QUICK]


# ════════════════════════════════════════════════════════════════════════
#  Special effects — the "god tier" living glyphs
# ════════════════════════════════════════════════════════════════════════

EffectKind = Literal["pulse", "ripple"]


@dataclass(frozen=True)
class SpecialEffect:
    """A named, width-safe, theme-aware living-glyph effect.

    `glyph` is asserted width-safe at registry-build time (and by the
    fitness check) so an effect can never be the thing that breaks a
    layout. `label` is the stable handle a theme or operator can refer to.
    """
    key: str
    name: str
    tagline: str
    description: str
    config: PulseConfig
    glyph: str
    base_hex: str
    kind: EffectKind = "pulse"
    length: int = 1               # ripple uses >1
    phase_step: float = 0.15      # ripple cell offset

    @property
    def label(self) -> str:
        return f"glyph-fx:{self.key}"


# The registry. Three are the originals from breathing_glyph (breath,
# heartbeat, urgent); the rest are the 4.8 additions. Every glyph here is
# width-safe (the fitness check enforces it).
SPECIAL_EFFECTS: tuple[SpecialEffect, ...] = (
    SpecialEffect(
        key="breath", name="Breath", tagline="slow, calm pulse",
        description=(
            "A 4-second sine-wave glow. The resting state — an idle "
            "indicator that proves the system is alive without demanding "
            "attention."
        ),
        config=BREATH, glyph=_g.LOZENGE, base_hex="#7DD3FC", kind="pulse",
    ),
    SpecialEffect(
        key="heartbeat", name="Heartbeat", tagline="the beating heart",
        description=(
            "The two-beat cardiac glow behind the status-bar heart. This "
            "IS the pulsing red background you asked about — generalized "
            "into a reusable effect. ~60bpm, calming not anxious. Active-"
            "work indicator."
        ),
        config=HEARTBEAT, glyph="\u2665", base_hex="#FF6B6B", kind="pulse",
    ),
    SpecialEffect(
        key="urgent", name="Urgent Blink", tagline="sharp, fast alert",
        description=(
            "A 0.6-second hard blink. Reserved for alert-class state — when "
            "something needs eyes on it now."
        ),
        config=URGENT_BLINK, glyph="\u2738", base_hex="#FB7185",
        kind="pulse",
    ),
    SpecialEffect(
        key="shimmer", name="Shimmer", tagline="subtle living sparkle",
        description=(
            "A fast, low-amplitude flicker — like light catching a facet. "
            "Decorative accent that never quite holds still."
        ),
        config=SHIMMER, glyph="\u2727", base_hex="#A78BFA", kind="pulse",
    ),
    SpecialEffect(
        key="beacon", name="Beacon", tagline="lighthouse sweep",
        description=(
            "A slow, high-amplitude swell from near-dark to full bright and "
            "back. A patient signal — I'm here, look when you're ready."
        ),
        config=BEACON, glyph="\u25C9", base_hex="#5EEAD4", kind="pulse",
    ),
    SpecialEffect(
        key="starlight", name="Starlight", tagline="twinkling star",
        description=(
            "A four-pointed star on a gentle, slightly irregular glow. The "
            "cosmos, made of one safe cell."
        ),
        config=STARLIGHT, glyph="\u2726", base_hex="#FCD34D", kind="pulse",
    ),
    SpecialEffect(
        key="ripple", name="Ripple", tagline="light rippling along a border",
        description=(
            "A row of glyphs pulsing out-of-phase, so the glow travels along "
            "the line instead of blinking in unison. The 'modern usable UI "
            "object for decor' — drop it under a title or along a frame."
        ),
        config=BREATH, glyph=_g.LOZENGE, base_hex="#7DD3FC", kind="ripple",
        length=18, phase_step=0.16,
    ),
    SpecialEffect(
        key="frame", name="Ripple Frame", tagline="a glow circling a whole border",
        description=(
            "Ripple, taken all the way around a rectangle: the wave travels "
            "the full perimeter — top, right, bottom, left, through the "
            "corners — so a glow glides around an entire frame while the "
            "border itself stays solid. This is what now wraps the cockpit's "
            "main 4-window container and (opt-in) the GlyphStage. See "
            "ripple_border.py / RippleFrame; the trough stays visible so it "
            "reads as a living frame, never marching ants."
        ),
        config=BREATH, glyph=_g.LOZENGE, base_hex="#A78BFA", kind="ripple",
        length=24, phase_step=0.14,
    ),
    SpecialEffect(
        key="aurora_frame", name="Aurora Frame",
        tagline="a rainbow that ripples around a whole border",
        description=(
            "Ripple Frame + Aurora at once: a full spectrum is wrapped around "
            "the perimeter and rotates slowly over time (the GlyphStage aurora "
            "glyph's smooth hue-cycle), while a brightness glow still ripples "
            "around the frame. Theme-independent — it paints its own rainbow. "
            "Live on the Cosmic Fitness GlyphStage border; available to any "
            "frame via mode 'aurora', and to any theme via "
            "effects.ripple.hue_cycle = true. See ripple_border.RIPPLE_AURORA."
        ),
        config=BREATH, glyph=_g.LOZENGE, base_hex="#A78BFA", kind="ripple",
        length=24, phase_step=0.14,
    ),
)


def special_effects() -> tuple[SpecialEffect, ...]:
    return SPECIAL_EFFECTS


def effect_by_key(key: str) -> SpecialEffect | None:
    for fx in SPECIAL_EFFECTS:
        if fx.key == key:
            return fx
    return None


# ════════════════════════════════════════════════════════════════════════
#  Glyph animations — frame-cycling "living glyphs" (v0.2.42)
# ════════════════════════════════════════════════════════════════════════
#
# Distinct from special effects (which modulate *brightness* of one glyph via
# a sine wave), an animation cycles through a *sequence of frames*. Each frame
# is a single glyph (or short cluster). Two safety tiers:
#
#   • layout-safe  — every frame is one cell (safe/convention). Runs anywhere,
#                    including the main UI, without risk of width jitter.
#   • sandbox-only — at least one frame is emoji/wide/composite. Lovely, but it
#                    must live inside a GlyphStage so its width can't shift the
#                    surrounding layout. (This is exactly the dancing-emoji case
#                    — 🕺💃 — confined to the sandbox where it's harmless.)
#
# is_layout_safe is computed from classify_glyph, so an animation can never
# *claim* to be layout-safe while smuggling a wide frame — the fitness check
# verifies it.

AnimationTier = Literal["layout-safe", "sandbox-only"]


@dataclass(frozen=True)
class AnimationSpec:
    """A named, frame-cycling glyph animation."""
    key: str
    name: str
    tagline: str
    frames: tuple[str, ...]
    fps: float = 8.0
    description: str = ""

    @property
    def label(self) -> str:
        return f"glyph-anim:{self.key}"

    @property
    def interval(self) -> float:
        """Seconds between frames."""
        return 1.0 / self.fps if self.fps > 0 else 0.125

    @property
    def is_layout_safe(self) -> bool:
        """True iff every frame renders one cell (safe/convention)."""
        return all(
            classify_glyph(f)[0] in ("safe", "convention") for f in self.frames
        )

    @property
    def is_universal(self) -> bool:
        """True iff every frame is provably one cell on every terminal.

        Frame-cycling animations rendered in a bordered, width-counted layout
        must be universal, or a wider frame shifts that line's border.
        """
        return all(is_universal_width(f) for f in self.frames)

    @property
    def tier(self) -> AnimationTier:
        return "layout-safe" if self.is_layout_safe else "sandbox-only"

    @property
    def worst_status(self) -> GlyphStatus:
        order = ["safe", "convention", "emoji", "wide", "composite"]
        worst = "safe"
        for f in self.frames:
            st = classify_glyph(f)[0]
            if order.index(st) > order.index(worst):
                worst = st
        return worst  # type: ignore[return-value]


# The catalog. Layout-safe animations use single-cell glyphs (braille, blessed
# block elements, circles, four/six-pointed stars). Sandbox-only ones use wide
# emoji and are meant for a GlyphStage.
ANIMATIONS: tuple[AnimationSpec, ...] = (
    AnimationSpec(
        key="spinner", name="Spinner", tagline="the classic braille spinner",
        frames=tuple("\u280B\u2819\u2839\u2838\u283C\u2834\u2826\u2827\u2807\u280F"),
        fps=10.0,
        description="A smooth 10-fps braille spinner — the universal 'working' "
                    "indicator. Single-cell on every terminal.",
    ),
    AnimationSpec(
        key="orbit", name="Orbit", tagline="a dot circling",
        frames=tuple("\u2808\u2810\u2820\u2880\u2840\u2804\u2802\u2801"),
        fps=12.0,
        description="One braille dot tracing a circle — a quieter spinner for "
                    "subtle 'thinking' states.",
    ),
    AnimationSpec(
        key="pulse", name="Pulse Dots", tagline="a breathing row of dots",
        frames=("\u2801", "\u2803", "\u2807", "\u280F", "\u281F", "\u280F",
                "\u2807", "\u2803"),
        fps=8.0,
        description="Braille dots filling and emptying — a gentle level/activity "
                    "pulse.",
    ),
    AnimationSpec(
        key="bar", name="Level Bar", tagline="a bouncing level meter",
        frames=("\u2581", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586",
                "\u2587", "\u2588", "\u2587", "\u2586", "\u2585", "\u2584",
                "\u2583", "\u2582"),
        fps=12.0,
        description="A single cell rising and falling through the block "
                    "elements — a VU-meter feel. Layout-safe (blocks are "
                    "blessed-narrow).",
    ),
    AnimationSpec(
        key="ring", name="Pulse Ring", tagline="a shaded bloom",
        frames=(" ", "\u2591", "\u2592", "\u2593", "\u2588", "\u2593",
                "\u2592", "\u2591"),
        fps=8.0,
        description="A cell blooming from empty through the shading blocks to "
                    "full and back — a soft radar/heartbeat pulse built from "
                    "block elements, which are one cell on every terminal.",
    ),
    AnimationSpec(
        key="twinkle", name="Twinkle", tagline="a braille sparkle",
        frames=("\u2801", "\u2803", "\u2807", "\u280F", "\u283F", "\u280F",
                "\u2807", "\u2803"),
        fps=7.0,
        description="A braille spark swelling and settling — braille is one "
                    "cell on every terminal, so this never shifts a border.",
    ),
    # ── sandbox-only (wide / emoji) — for a GlyphStage ───────────────────────
    AnimationSpec(
        key="moon", name="Moon Phases", tagline="the moon waxing & waning",
        frames=("\U0001F311", "\U0001F312", "\U0001F313", "\U0001F314",
                "\U0001F315", "\U0001F316", "\U0001F317", "\U0001F318"),
        fps=6.0,
        description="The eight lunar phases cycling. Wide emoji — beautiful, "
                    "and perfectly safe inside a GlyphStage.",
    ),
    AnimationSpec(
        key="dance", name="Dancing", tagline="the dancing duo",
        frames=("\U0001F57A", "\U0001F483", "\U0001F57A", "\U0001F483"),
        fps=4.0,
        description="The dancing-emoji you wanted — 🕺💃 — running for real, "
                    "boxed in a GlyphStage so it can't shake the UI loose.",
    ),
    AnimationSpec(
        key="sparkle", name="Sparkle Show", tagline="emoji sparkle cycle",
        frames=("\u2728", "\U0001F4AB", "\u2B50", "\U0001F31F"),
        fps=5.0,
        description="A cycle of sparkle emoji — the celebratory one. Sandbox-"
                    "only.",
    ),
)


def animations() -> tuple[AnimationSpec, ...]:
    return ANIMATIONS


def animation_by_key(key: str) -> AnimationSpec | None:
    for a in ANIMATIONS:
        if a.key == key:
            return a
    return None


# ════════════════════════════════════════════════════════════════════════
#  Animated special effects — frames + a glow or hue cycle (v0.2.42)
# ════════════════════════════════════════════════════════════════════════
#
# The synthesis of the two layers above: a frame sequence (animation) that is
# ALSO modulated in brightness ("glow") or colour ("hue"). The beating
# status-bar heart is the archetype — ♥ swapping to ♡ while the red halo
# pulses. The pure colour/timing maths live here (no Textual) so they're
# testable; the AnimatedEffect widget in animated_glyph.py renders them.

EffectAnimMode = Literal["glow", "hue"]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def blend(base: tuple[int, int, int], bg: tuple[int, int, int],
          alpha: float) -> tuple[int, int, int]:
    """Fake alpha: blend base toward bg. alpha=1 → base, alpha=0 → bg."""
    a = max(0.0, min(1.0, alpha))
    return tuple(bg[i] + (base[i] - bg[i]) * a for i in range(3))  # type: ignore


def sine_alpha(elapsed: float, period: float, amplitude: float,
               midpoint: float) -> float:
    """Brightness in [0,1] following a sine wave, clamped to a valid range."""
    if period <= 0:
        return midpoint
    phase = (elapsed % period) / period
    val = midpoint + amplitude * 0.5 * math.sin(2 * math.pi * phase)
    return max(0.0, min(1.0, val))


def hue_rotate(base: tuple[int, int, int], elapsed: float,
               period: float) -> tuple[int, int, int]:
    """Rotate the hue of `base` once per `period` seconds (the Aurora shift)."""
    r, g, b = (c / 255.0 for c in base)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if period > 0:
        h = (h + (elapsed % period) / period) % 1.0
    nr, ng, nb = colorsys.hsv_to_rgb(h, max(s, 0.55), max(v, 0.8))
    return (nr * 255, ng * 255, nb * 255)


def effect_color_at(spec: AnimatedEffectSpec, elapsed: float) -> str:
    """The hex colour an animated effect should paint at `elapsed` seconds."""
    base = _hex_to_rgb(spec.base_hex)
    if spec.mode == "hue":
        return _rgb_to_hex(hue_rotate(base, elapsed, spec.hue_period))
    bg = _hex_to_rgb(spec.bg_hex)
    a = sine_alpha(elapsed, spec.pulse_period, spec.amplitude, spec.midpoint)
    return _rgb_to_hex(blend(base, bg, a))


@dataclass(frozen=True)
class AnimatedEffectSpec:
    """A frame-cycling effect with brightness ('glow') or colour ('hue')
    modulation — the union of an animation and a special effect."""
    key: str
    name: str
    tagline: str
    frames: tuple[str, ...]
    base_hex: str = "#FF6B6B"
    bg_hex: str = "#101018"
    mode: EffectAnimMode = "glow"
    frame_fps: float = 6.0
    pulse_period: float = 2.0      # seconds per brightness cycle (glow)
    amplitude: float = 0.6
    midpoint: float = 0.6
    hue_period: float = 6.0        # seconds per full hue rotation (hue)
    description: str = ""

    @property
    def label(self) -> str:
        return f"glyph-fxanim:{self.key}"

    @property
    def frame_interval(self) -> float:
        return 1.0 / self.frame_fps if self.frame_fps > 0 else 0.16

    @property
    def is_layout_safe(self) -> bool:
        return all(
            classify_glyph(f)[0] in ("safe", "convention") for f in self.frames
        )

    @property
    def is_universal(self) -> bool:
        """True iff every frame is provably one cell on every terminal."""
        return all(is_universal_width(f) for f in self.frames)

    @property
    def tier(self) -> AnimationTier:
        return "layout-safe" if self.is_layout_safe else "sandbox-only"

    @property
    def worst_status(self) -> GlyphStatus:
        order = ["safe", "convention", "emoji", "wide", "composite"]
        worst = "safe"
        for f in self.frames:
            st = classify_glyph(f)[0]
            if order.index(st) > order.index(worst):
                worst = st
        return worst  # type: ignore[return-value]


# The catalog. Layout-safe ones run anywhere; the moon glow is sandbox-only.
ANIMATED_EFFECTS: tuple[AnimatedEffectSpec, ...] = (
    AnimatedEffectSpec(
        key="beat", name="Beating Heart", tagline="frames + cardiac glow",
        frames=("\u2665", "\u2665", "\u2665", "\u2661"),
        base_hex="#FF4D6D", bg_hex="#1A0008", mode="glow",
        frame_fps=4.0, pulse_period=1.0, amplitude=0.7, midpoint=0.62,
        description="The status-bar heart, generalized: ♥ swaps to ♡ on the "
                    "rest beat while the red halo pulses at ~60bpm. The "
                    "archetypal animated effect — frame change AND glow.",
    ),
    AnimatedEffectSpec(
        key="spin_glow", name="Glowing Spinner", tagline="spinner + breath",
        frames=tuple("\u280B\u2819\u2839\u2838\u283C\u2834\u2826\u2827\u2807\u280F"),
        base_hex="#7DD3FC", bg_hex="#06121A", mode="glow",
        frame_fps=10.0, pulse_period=2.4, amplitude=0.5, midpoint=0.7,
        description="A braille spinner that also breathes — a 'working' "
                    "indicator with a soft cyan pulse layered on the spin.",
    ),
    AnimatedEffectSpec(
        key="twinkle_glow", name="Twinkle Glow", tagline="braille spark + shimmer",
        frames=("\u2801", "\u2803", "\u2807", "\u280F", "\u283F", "\u280F",
                "\u2807", "\u2803"),
        base_hex="#FDE68A", bg_hex="#14110A", mode="glow",
        frame_fps=7.0, pulse_period=1.6, amplitude=0.8, midpoint=0.6,
        description="A braille spark swelling while its brightness shimmers — "
                    "sparkle with depth, one cell on every terminal.",
    ),
    AnimatedEffectSpec(
        key="aurora", name="Aurora", tagline="hue-cycling swatch",
        frames=("\u2588",),
        base_hex="#A78BFA", mode="hue",
        frame_fps=1.0, hue_period=8.0,
        description="A full-block swatch whose colour drifts slowly around the "
                    "spectrum — purple → blue → teal → back. A nod to the "
                    "Aurora theme's colour shift; the block is one cell "
                    "everywhere, so the colour moves but the border never does.",
    ),
    AnimatedEffectSpec(
        key="aurora_heart", name="Aurora Heart", tagline="a heart that shifts hue",
        frames=("\u2665",),
        base_hex="#FF6B9D", mode="hue",
        frame_fps=1.0, hue_period=7.0,
        description="The Aurora shift, given a heart: ♥ drifts slowly through "
                    "the whole spectrum — rose → amber → green → cyan → violet "
                    "→ back — a living, colour-changing heart. The heart is a "
                    "blessed one-cell (convention) glyph, so the colour moves "
                    "but the layout never does. Love, in every hue. <3",
    ),
    AnimatedEffectSpec(
        key="moon_glow", name="Glowing Moon", tagline="moon phases + glow",
        frames=("\U0001F311", "\U0001F312", "\U0001F313", "\U0001F314",
                "\U0001F315", "\U0001F316", "\U0001F317", "\U0001F318"),
        base_hex="#E5E7EB", bg_hex="#0B0B14", mode="glow",
        frame_fps=6.0, pulse_period=4.0, amplitude=0.35, midpoint=0.85,
        description="The lunar cycle with a gentle glow. Wide emoji — "
                    "sandbox-only, lovely inside a GlyphStage.",
    ),
)


def animated_effects() -> tuple[AnimatedEffectSpec, ...]:
    return ANIMATED_EFFECTS


def animated_effect_by_key(key: str) -> AnimatedEffectSpec | None:
    for a in ANIMATED_EFFECTS:
        if a.key == key:
            return a
    return None


# ════════════════════════════════════════════════════════════════════════
#  The fitness report
# ════════════════════════════════════════════════════════════════════════

@dataclass
class GlyphIssue:
    """A glyph in the live source scan that warrants a look."""
    char: str
    codepoint: str
    unicode_name: str
    status: GlyphStatus
    occurrences: int
    safe_alternative: str | None


@dataclass
class FitnessReport:
    """The verdict of a Cosmic Fitness check.

    The PASS criterion is deliberately deterministic and about *internal
    consistency*, not about a live filesystem (which would make the check
    flaky). Specifically, the system is FIT when:

      • every special-effect glyph is width-safe, and every effect config
        is structurally valid (positive period/tick, sane amplitude), and
      • every curated GlyphSpec's stored status matches a fresh
        classify_glyph (no label can drift from Unicode reality).

    The live source scan, when included, contributes informational counts
    and a list of composite-glyph issues — surfaced so the operator can
    act, but NOT used to fail the check.
    """
    generated_at: str
    # inventory counts (curated)
    total_glyphs: int
    safe: int
    convention: int
    emoji: int
    wide: int
    composite: int
    # effects
    effects_total: int
    effects_ok: bool
    effect_problems: list[str] = field(default_factory=list)
    # animations (v0.2.42)
    animations_total: int = 0
    animations_layout_safe: int = 0
    animations_sandbox: int = 0
    animations_ok: bool = True
    animation_problems: list[str] = field(default_factory=list)
    # animated special effects (v0.2.42)
    animated_effects_total: int = 0
    animated_effects_ok: bool = True
    animated_effect_problems: list[str] = field(default_factory=list)
    # consistency
    consistency_ok: bool = True
    consistency_problems: list[str] = field(default_factory=list)
    # live scan (informational)
    scanned_files: int = 0
    scan_composite_issues: list[GlyphIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.effects_ok and self.consistency_ok
            and self.animations_ok and self.animated_effects_ok
        )

    @property
    def grade(self) -> str:
        return "STRONG" if self.passed else "NEEDS ATTENTION"

    @property
    def summary(self) -> str:
        return (
            f"Cosmic Fitness: {self.grade} — "
            f"{self.total_glyphs} glyphs "
            f"({self.safe} safe / {self.convention} convention / "
            f"{self.emoji} emoji / {self.wide} wide / {self.composite} composite), "
            f"{self.effects_total} special effects "
            f"({'all clean' if self.effects_ok else 'PROBLEMS'}), "
            f"{self.animations_total} animations "
            f"({self.animations_layout_safe} layout-safe / "
            f"{self.animations_sandbox} sandbox), "
            f"{self.animated_effects_total} animated effects "
            f"({'all clean' if self.animated_effects_ok else 'PROBLEMS'})."
        )

    def render_lines(self) -> list[str]:
        """A plain, copy-pasteable report (rich-markup ok)."""
        ok = self.passed
        head = "[bold green]✓ STRONG[/bold green]" if ok else \
               "[bold yellow]! NEEDS ATTENTION[/bold yellow]"
        lines = [
            f"{head}  [b]Cosmic Fitness[/b]  [dim]{self.generated_at}[/dim]",
            "",
            "[b]glyph inventory[/b]",
            f"  ✓ safe        {self.safe:>3}   one cell everywhere",
            f"  ◊ convention  {self.convention:>3}   ambiguous but blessed-narrow",
            f"  ◉ emoji       {self.emoji:>3}   narrow by spec, 2 cells in practice",
            f"  ▸ wide        {self.wide:>3}   two cells — chat-only",
            f"  ✗ composite   {self.composite:>3}   multi-codepoint — TUI-risky",
            f"  ─ total       {self.total_glyphs:>3}",
            "",
            "[b]special effects[/b]",
        ]
        if self.effects_ok:
            lines.append(
                f"  [green]✓[/green] {self.effects_total} effects, "
                f"all glyphs width-safe, all configs valid"
            )
        else:
            lines.append(f"  [red]✗[/red] {len(self.effect_problems)} problem(s):")
            for p in self.effect_problems:
                lines.append(f"      [red]·[/red] {p}")
        lines.append("")
        lines.append("[b]glyph animations[/b]")
        if self.animations_ok:
            lines.append(
                f"  [green]✓[/green] {self.animations_total} animations "
                f"({self.animations_layout_safe} layout-safe, "
                f"{self.animations_sandbox} sandbox-only), all frames valid"
            )
        else:
            lines.append(f"  [red]✗[/red] {len(self.animation_problems)} problem(s):")
            for p in self.animation_problems:
                lines.append(f"      [red]·[/red] {p}")
        lines.append("")
        lines.append("[b]animated special effects[/b]")
        if self.animated_effects_ok:
            lines.append(
                f"  [green]✓[/green] {self.animated_effects_total} animated "
                f"effects, all frames + modulation valid"
            )
        else:
            lines.append(
                f"  [red]✗[/red] {len(self.animated_effect_problems)} problem(s):"
            )
            for p in self.animated_effect_problems:
                lines.append(f"      [red]·[/red] {p}")
        lines.append("")
        lines.append("[b]label consistency[/b]")
        if self.consistency_ok:
            lines.append("  [green]✓[/green] every curated label matches Unicode reality")
        else:
            lines.append(f"  [red]✗[/red] {len(self.consistency_problems)} mismatch(es):")
            for p in self.consistency_problems:
                lines.append(f"      [red]·[/red] {p}")
        if self.scanned_files:
            lines.append("")
            lines.append(f"[b]live source scan[/b]  [dim]({self.scanned_files} files)[/dim]")
            if self.scan_composite_issues:
                lines.append(
                    f"  [yellow]![/yellow] {len(self.scan_composite_issues)} "
                    "composite glyph(s) found in source — review:"
                )
                for iss in self.scan_composite_issues[:12]:
                    alt = f"  → safe: {iss.safe_alternative}" if iss.safe_alternative else ""
                    lines.append(
                        f"      {iss.codepoint}  {iss.unicode_name[:34]:<34} "
                        f"×{iss.occurrences}{alt}"
                    )
            else:
                lines.append("  [green]✓[/green] no composite (VS16/ZWJ) glyphs in source")
        for n in self.notes:
            lines.append(f"[dim]{n}[/dim]")
        return lines

    def render_text(self) -> str:
        return "\n".join(self.render_lines())


def _validate_effect(fx: SpecialEffect) -> list[str]:
    """Return a list of problems with one effect (empty = healthy).

    An effect glyph animates inside a width-counted row, so it must be truly
    one-cell — not merely EAW-narrow. We therefore require its *classification*
    to be safe or convention, which rejects the emoji-variation trap (❤ ▶ ☄)
    that a bare EAW check would wave through.
    """
    problems: list[str] = []
    status, _eaw, name, _cp = classify_glyph(fx.glyph)
    if status not in ("safe", "convention"):
        problems.append(
            f"{fx.label}: glyph {fx.glyph!r} ({name}) classifies as "
            f"'{status}' — not layout-safe for an animated cell"
        )
    c = fx.config
    if c.period_seconds <= 0:
        problems.append(f"{fx.label}: period_seconds must be > 0 (got {c.period_seconds})")
    if c.tick_seconds <= 0:
        problems.append(f"{fx.label}: tick_seconds must be > 0 (got {c.tick_seconds})")
    if not (0.0 <= c.amplitude <= 1.0):
        problems.append(f"{fx.label}: amplitude out of [0,1] (got {c.amplitude})")
    if not (0.0 <= c.midpoint <= 1.0):
        problems.append(f"{fx.label}: midpoint out of [0,1] (got {c.midpoint})")
    if fx.kind == "ripple" and fx.length < 2:
        problems.append(f"{fx.label}: ripple needs length >= 2 (got {fx.length})")
    return problems


# The canonical layout-safe animations. These MUST stay one-cell on every
# frame; if an edit makes one sandbox-only, the fitness check fails so the
# regression is caught immediately.
_LAYOUT_SAFE_ANIM_KEYS: frozenset[str] = frozenset({
    "spinner", "orbit", "pulse", "bar", "ring", "twinkle",
})


def _validate_animation(an: AnimationSpec) -> list[str]:
    """Return a list of problems with one animation (empty = healthy)."""
    problems: list[str] = []
    if not an.frames:
        problems.append(f"{an.label}: has no frames")
    if an.fps <= 0:
        problems.append(f"{an.label}: fps must be > 0 (got {an.fps})")
    if an.key in _LAYOUT_SAFE_ANIM_KEYS and not an.is_layout_safe:
        bad = [
            f"{f!r}({classify_glyph(f)[0]})"
            for f in an.frames
            if classify_glyph(f)[0] not in ("safe", "convention")
        ]
        problems.append(
            f"{an.label}: declared layout-safe but has non-one-cell frame(s): "
            f"{', '.join(bad)}"
        )
    return problems


def _validate_animated_effect(an: AnimatedEffectSpec) -> list[str]:
    """Return a list of problems with one animated effect (empty = healthy)."""
    problems: list[str] = []
    if not an.frames:
        problems.append(f"{an.label}: has no frames")
    if an.frame_fps <= 0:
        problems.append(f"{an.label}: frame_fps must be > 0 (got {an.frame_fps})")
    if not (0.0 <= an.amplitude <= 1.0):
        problems.append(f"{an.label}: amplitude out of [0,1] (got {an.amplitude})")
    if not (0.0 <= an.midpoint <= 1.0):
        problems.append(f"{an.label}: midpoint out of [0,1] (got {an.midpoint})")
    if an.mode == "glow" and an.pulse_period <= 0:
        problems.append(f"{an.label}: pulse_period must be > 0 for glow")
    if an.mode == "hue" and an.hue_period <= 0:
        problems.append(f"{an.label}: hue_period must be > 0 for hue")
    return problems


def run_cosmic_fitness(
    data_dir: Path | None = None,
    include_scan: bool = False,
) -> FitnessReport:
    """Run the visual-systems health check.

    `include_scan=True` walks the source tree (via glyph_sentinel) and adds
    informational composite-glyph findings. It's off by default so the core
    check stays fast and deterministic; the cockpit turns it on.
    """
    cats = curated_categories()
    all_specs = [s for c in cats for s in c.glyphs]

    safe = sum(1 for s in all_specs if s.status == "safe")
    convention = sum(1 for s in all_specs if s.status == "convention")
    emoji = sum(1 for s in all_specs if s.status == "emoji")
    wide = sum(1 for s in all_specs if s.status == "wide")
    composite = sum(1 for s in all_specs if s.status == "composite")

    # effects health
    effect_problems: list[str] = []
    for fx in SPECIAL_EFFECTS:
        effect_problems.extend(_validate_effect(fx))
    effects_ok = not effect_problems

    # label consistency: stored status must match a fresh classification
    consistency_problems: list[str] = []
    for s in all_specs:
        fresh_status, fresh_eaw, *_ = classify_glyph(s.char)
        if fresh_status != s.status:
            consistency_problems.append(
                f"{s.codepoint} '{s.label}': stored {s.status}, "
                f"reality {fresh_status}"
            )
    consistency_ok = not consistency_problems

    # animations health (v0.2.42)
    animation_problems: list[str] = []
    for an in ANIMATIONS:
        animation_problems.extend(_validate_animation(an))
    animations_ok = not animation_problems
    anims_layout_safe = sum(1 for a in ANIMATIONS if a.is_layout_safe)
    anims_sandbox = len(ANIMATIONS) - anims_layout_safe

    # animated special effects health (v0.2.42)
    animated_effect_problems: list[str] = []
    for ae in ANIMATED_EFFECTS:
        animated_effect_problems.extend(_validate_animated_effect(ae))
    animated_effects_ok = not animated_effect_problems

    report = FitnessReport(
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_glyphs=len(all_specs),
        safe=safe, convention=convention, wide=wide, composite=composite,
        emoji=emoji,
        effects_total=len(SPECIAL_EFFECTS),
        effects_ok=effects_ok, effect_problems=effect_problems,
        animations_total=len(ANIMATIONS),
        animations_layout_safe=anims_layout_safe,
        animations_sandbox=anims_sandbox,
        animations_ok=animations_ok, animation_problems=animation_problems,
        animated_effects_total=len(ANIMATED_EFFECTS),
        animated_effects_ok=animated_effects_ok,
        animated_effect_problems=animated_effect_problems,
        consistency_ok=consistency_ok, consistency_problems=consistency_problems,
    )

    if include_scan:
        try:
            from ..stewardship import glyph_sentinel as _gs
            catalog = _gs.scan_source_tree()
            report.scanned_files = catalog.total_files_scanned
            # The sentinel scans char-by-char, so a composite emoji shows up
            # as its base + a separate U+FE0F / U+200D entry. We surface the
            # genuinely TUI-risky findings only: true-wide glyphs (EAW W/F —
            # the colour emoji) and the variation-selector / ZWJ markers
            # themselves (their mere presence means composite emoji exist in
            # source). Ambiguous text/math symbols (…, ∞, °, ∈) are fine and
            # would just be noise, so they're excluded.
            vs16, zwj = "\uFE0F", "\u200D"
            for entry in catalog.glyphs.values():
                ch = entry.char
                eaw = entry.east_asian_width
                is_marker = ch in (vs16, zwj)
                is_true_wide = eaw in ("W", "F")
                if not (is_marker or is_true_wide):
                    continue
                st = "composite" if is_marker else "wide"
                report.scan_composite_issues.append(GlyphIssue(
                    char=ch,
                    codepoint=entry.codepoint,
                    unicode_name=entry.name,
                    status=st,
                    occurrences=entry.total_occurrences,
                    safe_alternative=(entry.proposed_replacement
                                      or safe_alternative_for(ch)),
                ))
            report.scan_composite_issues.sort(key=lambda i: -i.occurrences)
        except Exception as exc:  # noqa: BLE001 — scan is best-effort
            report.notes.append(f"(live scan unavailable: {exc!r})")

    return report


# ════════════════════════════════════════════════════════════════════════
#  Verdict store — the operator can MARK glyphs
# ════════════════════════════════════════════════════════════════════════

Verdict = Literal["good", "replace", "remove"]
_VALID_VERDICTS = ("good", "replace", "remove")


class GlyphVerdictStore:
    """Persist operator verdicts on glyphs.

    Honors Kevin's ask: "the user can mark and list which ones need to be
    replaced or edited into a safe variant or removed entirely." Stored as a
    small JSON file in the data dir, keyed by codepoint string. Tier-1: this
    only records intent — it never edits source.
    """

    FILENAME = "glyph_verdicts.json"

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / self.FILENAME

    def _load_raw(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_raw(self, data: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def record(self, char: str, verdict: Verdict, note: str = "") -> dict:
        """Record a verdict for `char`. Returns the stored record."""
        if verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"verdict must be one of {_VALID_VERDICTS}, got {verdict!r}"
            )
        status, eaw, uname, cp = classify_glyph(char)
        data = self._load_raw()
        record = {
            "char": char,
            "codepoint": cp,
            "unicode_name": uname,
            "status": status,
            "verdict": verdict,
            "note": note,
            "suggested_alternative": safe_alternative_for(char),
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        data[cp] = record
        self._save_raw(data)
        return record

    def get(self, char: str) -> dict | None:
        _s, _e, _n, cp = classify_glyph(char)
        return self._load_raw().get(cp)

    def clear(self, char: str) -> bool:
        _s, _e, _n, cp = classify_glyph(char)
        data = self._load_raw()
        if cp in data:
            del data[cp]
            self._save_raw(data)
            return True
        return False

    def all(self) -> dict:
        return self._load_raw()

    def by_verdict(self, verdict: Verdict) -> list[dict]:
        return [r for r in self._load_raw().values()
                if r.get("verdict") == verdict]

    def summary(self) -> dict:
        data = self._load_raw()
        out = {"total": len(data), "good": 0, "replace": 0, "remove": 0}
        for r in data.values():
            v = r.get("verdict")
            if v in out:
                out[v] += 1
        return out

    def render_lines(self) -> list[str]:
        data = self._load_raw()
        if not data:
            return ["[dim]no glyph verdicts recorded yet.[/dim]",
                    "[dim]mark one with: /cosmic mark <glyph> good|replace|remove[/dim]"]
        s = self.summary()
        lines = [
            f"[b]glyph verdicts[/b]  "
            f"[green]{s['good']} good[/green] · "
            f"[yellow]{s['replace']} replace[/yellow] · "
            f"[red]{s['remove']} remove[/red]",
            "",
        ]
        badge = {"good": "[green]✓[/green]", "replace": "[yellow]→[/yellow]",
                 "remove": "[red]✗[/red]"}
        for cp in sorted(data.keys()):
            r = data[cp]
            alt = r.get("suggested_alternative")
            alt_s = f"  (safe: {alt})" if alt and r["verdict"] == "replace" else ""
            note_s = f"  — {r['note']}" if r.get("note") else ""
            lines.append(
                f"  {badge.get(r['verdict'], '·')} {r['char']}  "
                f"{r['codepoint']:<16} {r['unicode_name'][:30]}{alt_s}{note_s}"
            )
        return lines


__all__ = [
    # taxonomy
    "GlyphStatus", "STATUS_BADGE", "STATUS_LABEL", "STATUS_BLURB",
    "BLESSED_NARROW", "EMOJI_VARIATION_BASES", "classify_glyph",
    "SAFE_ALTERNATIVES", "safe_alternative_for",
    # inventory
    "GlyphSpec", "GlyphCategory", "curated_categories", "quick_picker_specs",
    # effects
    "EffectKind", "SpecialEffect", "SPECIAL_EFFECTS",
    "special_effects", "effect_by_key",
    # animations
    "AnimationTier", "AnimationSpec", "ANIMATIONS",
    "animations", "animation_by_key",
    # animated special effects
    "EffectAnimMode", "AnimatedEffectSpec", "ANIMATED_EFFECTS",
    "animated_effects", "animated_effect_by_key", "effect_color_at",
    "blend", "sine_alpha", "hue_rotate",
    # report
    "GlyphIssue", "FitnessReport", "run_cosmic_fitness",
    # verdicts
    "Verdict", "GlyphVerdictStore",
    # control
    "KILL_SWITCH_ENV", "cosmic_fitness_enabled",
]
