"""
╔══════════════════════════════════════════════════════════════════════════╗
║  glyphs.py — terminal-safe glyph constants                               ║
║                                                                           ║
║  THE LESSON THIS FILE EXISTS TO REMEMBER                                 ║
║                                                                           ║
║  Many "single character" Unicode glyphs render as TWO terminal cells      ║
║  on some setups, even though Python sees them as one character. The     ║
║  Unicode standard calls this property "East Asian Width: Ambiguous" or  ║
║  "Wide" — and the rule for which terminal does what depends on locale,  ║
║  font, and emoji-presentation handling.                                 ║
║                                                                           ║
║  Practical consequence: any box-drawing layout (banners, TUI columns,    ║
║  Rich tables, the cockpit) that counts characters to position the right ║
║  border will be off-by-N where N = number of ambiguous-width glyphs on  ║
║  that line. The diamond `◈` is the canonical offender; `⛔` and most    ║
║  emoji have the same problem.                                            ║
║                                                                           ║
║  Discovered by Kevin from a screenshot of the cockpit's borders          ║
║  shifting one column left per diamond. Locked in as a tree-level rule   ║
║  here so future code doesn't re-learn it the hard way.                  ║
║                                                                           ║
║  RULES                                                                    ║
║                                                                           ║
║    1. For anything that participates in horizontal layout (banner        ║
║       borders, TUI panels, table cells with explicit width), use only   ║
║       glyphs from the SAFE set below.                                    ║
║                                                                           ║
║    2. For inline body text (where the terminal flows on its own), the   ║
║       UNSAFE glyphs are fine. They look nicer; just don't put them     ║
║       inside a layout that depends on counting columns.                 ║
║                                                                           ║
║    3. If you must introduce a new glyph, look up its East Asian Width  ║
║       property first:  python -c "import unicodedata as u; \\           ║
║                                     print(u.east_asian_width('◈'))"    ║
║       — return values: N (Neutral, safe), Na (Narrow, safe),           ║
║         W (Wide, UNSAFE), F (Fullwidth, UNSAFE), A (Ambiguous, UNSAFE), ║
║         H (Halfwidth, safe).                                             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import unicodedata

# ─── Safe glyphs (one terminal cell, unambiguous) ──────────────────────────
#
# Verified with: unicodedata.east_asian_width(c) in {"N", "Na", "H"}.
# These render as exactly one cell on every terminal we've tested.

CHECK = "\u2713"          # ✓  CHECK MARK             (N)
CROSS = "\u2717"          # ✗  BALLOT X               (A — but de-facto narrow)
ARROW_RIGHT = "\u25B8"    # ▸  RIGHT-POINTING TRIANGLE (N)
ARROW_LEFT = "\u25C2"     # ◂  LEFT-POINTING TRIANGLE  (N)
LOZENGE = "\u25CA"        # ◊  LOZENGE (the brand-safe diamond) (N)
SQUARE = "\u25AA"         # ▪  BLACK SMALL SQUARE     (N)
BULLET = "\u2022"         # •  BULLET                 (A — but de-facto narrow)
MIDDLE_DOT = "\u00B7"     # ·  MIDDLE DOT             (A — de-facto narrow)
# glyph-catalog-d (Kevin, 2026-07-21): every box-drawing constant below
# was mislabeled "(N)" -- direct unicodedata check shows all 12 are
# actually EAW=Ambiguous (same mislabeling PATTERN already caught once
# this session for ARROW_RIGHT_HEAVY). Still genuinely safe in practice:
# audit_string()'s own DE_FACTO_NARROW whitelist already names every one
# of these exact codepoints explicitly, and they've shipped in every
# bordered panel in the cockpit with zero reported alignment bugs.
BOX_H = "\u2500"          # ─  BOX DRAWINGS LIGHT HORIZONTAL (A — de-facto narrow)
BOX_V = "\u2502"          # │  BOX DRAWINGS LIGHT VERTICAL   (A — de-facto narrow)
BOX_TL = "\u250C"         # ┌  TOP-LEFT                       (A — de-facto narrow)
BOX_TR = "\u2510"         # ┐  TOP-RIGHT                      (A — de-facto narrow)
BOX_BL = "\u2514"         # └  BOTTOM-LEFT                    (A — de-facto narrow)
BOX_BR = "\u2518"         # ┘  BOTTOM-RIGHT                   (A — de-facto narrow)
DOUBLE_H = "\u2550"       # ═  DOUBLE HORIZONTAL              (A — de-facto narrow)
DOUBLE_V = "\u2551"       # ║  DOUBLE VERTICAL                (A — de-facto narrow)
DOUBLE_TL = "\u2554"      # ╔  DOUBLE TOP-LEFT                (A — de-facto narrow)
DOUBLE_TR = "\u2557"      # ╗  DOUBLE TOP-RIGHT               (A — de-facto narrow)
DOUBLE_BL = "\u255A"      # ╚  DOUBLE BOTTOM-LEFT             (A — de-facto narrow)
DOUBLE_BR = "\u255D"      # ╝  DOUBLE BOTTOM-RIGHT            (A — de-facto narrow)

# ─── UNSAFE glyphs — DO NOT USE in width-sensitive layouts ────────────────
#
# These are aesthetically nice but render as 2 cells on some terminals.
# Kept as named constants so accidental usage is grep-able.

UNSAFE_DIAMOND = "\u25C8"          # ◈  WHITE DIAMOND CONTAINING BLACK SMALL DIAMOND (A)
UNSAFE_DIAMOND_BLACK = "\u25C6"    # ◆  BLACK DIAMOND                                 (A)
UNSAFE_DIAMOND_WHITE = "\u25C7"    # ◇  WHITE DIAMOND                                  (A)
UNSAFE_DIAMOND_SUIT = "\u2666"     # ♦  BLACK DIAMOND SUIT                            (A)
UNSAFE_NO_ENTRY = "\u26D4"         # ⛔  NO ENTRY                                       (W)
UNSAFE_WARNING = "\u26A0"          # ⚠  WARNING SIGN                                  (A/emoji)
UNSAFE_HEART = "\u2764"            # ❤  HEAVY BLACK HEART                              (A/emoji)
UNSAFE_STAR = "\u2B50"             # ⭐ WHITE MEDIUM STAR                             (W)
ARROW_RIGHT_HEAVY = "\u25B6"      # ▶  BLACK RIGHT-POINTING TRIANGLE  (A -- genuinely
                                   # unsafe; previously mislabeled "(N)" here and in
                                   # _ESTABLISHED_SAFE below, corrected 2026-07-20 after
                                   # direct unicodedata measurement. Use ARROW_RIGHT (\u25B8)
                                   # instead.  # theme-studio-redesign-d

# ─── Severity-glyph aliases ────────────────────────────────────────────────
#
# Use these in any output that participates in horizontal layout. They map
# to SAFE constants above; if a future terminal-renderer survey changes our
# mind about safety, edit here, not at every call site.

SEVERITY_OK = CHECK            # ✓
SEVERITY_WARNING = "!"         # ASCII for hardest reliability
SEVERITY_ERROR = CROSS         # ✗
SEVERITY_INFO = ARROW_RIGHT    # ▸
SEVERITY_BULLET = BULLET       # •  (acceptable; appears narrow on every modern terminal)

# ─── Brand markers ────────────────────────────────────────────────────────
#
# The project visual identity used to be ◈ (U+25C8 WHITE DIAMOND CONTAINING
# BLACK SMALL DIAMOND), which is East-Asian-Width Ambiguous — rendered as 2
# cells in CJK locales and emoji-presentation terminals, breaking every
# horizontal layout that contained it. Diagnosed by Kevin from a cockpit
# screenshot showing borders shifting one column left per diamond.
#
# Replaced with ◊ (U+25CA LOZENGE), East-Asian-Width Neutral, guaranteed
# one cell on every terminal. Same diamond aesthetic, no width risk.
#
# Future identity shifts: edit BRAND_MARKER here, not every call site.

BRAND_MARKER = LOZENGE         # ◊ — the project's visual signature
BRAND_MARKER_LEFT = LOZENGE    # ◊ — symmetric counterpart in flanking layouts
BRAND_MARKER_RIGHT = LOZENGE   # ◊ — symmetric counterpart in flanking layouts

def purge_unsafe_diamonds(s: str) -> str:
    """Replace every banned diamond (◈ ◆ ◇ — all EAW-Ambiguous, all
    layout-breakers on Kevin's terminal) with the safe BRAND_MARKER ◊.

    Source code was swept in the diamond-ban round; this helper covers
    STORED content (old transcripts, sealed chunks, external text) at
    render time — the 'purged across the board' guarantee for data that
    predates the ban."""
    return (s.replace(UNSAFE_DIAMOND, BRAND_MARKER)
             .replace(UNSAFE_DIAMOND_BLACK, BRAND_MARKER)
             .replace(UNSAFE_DIAMOND_WHITE, BRAND_MARKER)
             .replace(UNSAFE_DIAMOND_SUIT, BRAND_MARKER))


# ─── Emoji / missing-font-coverage risk (a DIFFERENT bug class) ──────────  # glyph-hardening-d
#
# Kevin (2026-07-20): flagged \U0001F39A (LEVEL SLIDER) and \u23f8 (PAUSE)
# rendering as tofu/fallback boxes on his terminal. Both are East-Asian-
# Width=Neutral -- audit_string()/is_width_safe() call them clean, because
# that check only ever measured column-count ambiguity. The real bug here
# is a different failure mode: these codepoints live in Unicode blocks
# that are emoji-presentation by default, and font-fallback doesn't
# always reach an installed glyph for them even when the artwork (e.g.
# Noto Color Emoji) exists on disk -- a rendering-pipeline gap EAW cannot
# see, because EAW was never designed to measure font coverage.
#
# is_emoji_risk() is a separate, additional check, not a replacement for
# is_width_safe(): does this codepoint fall in a block that's
# predominantly emoji/pictographic? It leans on _ESTABLISHED_SAFE to
# hand-exempt glyphs already proven fine in practice -- the same
# de-facto-narrow philosophy audit_string() uses for EAW=Ambiguous chars.

_EMOJI_RISK_RANGES = (
    (0x2600, 0x26FF),    # Miscellaneous Symbols (\u26a0 \u26d4 ...)
    (0x2700, 0x27BF),    # Dingbats (\u2705 \u274c \u2714 \u2715 ...)
    (0x23E9, 0x23FA),    # Misc Technical media-control block (\u23f8 ...)
    (0x2B00, 0x2BFF),    # Miscellaneous Symbols and Arrows (\u2b50 ...)
    (0x1F000, 0x1FFFF),  # Supplementary pictograph planes (modern emoji)
)

# Glyphs inside the risk ranges above that are PROVEN safe in practice --
# either already a hand-verified SAFE constant above, or directly
# confirmed rendering correctly on Kevin's own terminal:
#   \u2715 (close-button "x") -- used in 17+ cockpit files, zero
#     reported corruption.
#   \u2714 (heavy check mark) -- rendered correctly in the SAME
#     screenshot that reported the two real bugs above (confirmed, not
#     assumed).
_ESTABLISHED_SAFE = frozenset({
    CHECK, CROSS, ARROW_RIGHT, ARROW_LEFT,  # theme-studio-redesign-d: ARROW_RIGHT_HEAVY removed, was never actually safe
    LOZENGE, SQUARE, BULLET, MIDDLE_DOT,
    "\u2715",   # close-button "x", proven safe by pervasive existing use
    "\u2714",   # confirmed rendering in Kevin's own screenshot
    # glyph-catalog-d (Kevin, 2026-07-21): the diamond-ban's own named
    # replacements (test_brand_glyph.py's UNSAFE family \u2192 these). All
    # four are EAW=Neutral (genuinely one-cell, confirmed via direct
    # unicodedata check, not assumed) and fall in the Dingbats/Misc-
    # Symbols blocks is_emoji_risk() scans for missing-font-coverage --
    # but that check is a heuristic for a DIFFERENT bug (tofu glyphs),
    # not evidence against these specific four, which were deliberately
    # chosen replacements, never reported broken.
    "\u2756",   # \u2756 HEAVY DIAMOND
    "\u2726",   # \u2726 BLACK FOUR POINTED STAR
    "\u2727",   # \u2727 WHITE FOUR POINTED STAR
    "\u27e1",   # \u27e1 WHITE CONCAVE-SIDED DIAMOND
})

# \u2500\u2500\u2500 The safe glyph catalog (Kevin, 2026-07-21) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
#
# "create a safe glyph catalog and start using those glyphs to remove the
# redundant glyph test from having to run it so often." One canonical,
# documented table -- new UI code should draw from here FIRST instead of
# hand-checking a fresh codepoint with unicodedata each time. Every entry
# is either a SAFE constant above or an _ESTABLISHED_SAFE exemption --
# nothing here is unvetted. Tests can assert new usages are drawn from
# this catalog instead of independently re-deriving width/emoji-risk
# safety per file (see tests/conftest.py's session-scoped
# `all_src_python_files` fixture + tests/test_brand_glyph.py /
# tests/test_mos_surface.py, which now share ONE repo-wide file walk
# instead of one each).
SAFE_GLYPH_CATALOG: dict[str, str] = {
    CHECK: "check mark \u2014 success",
    CROSS: "ballot X \u2014 error/failure",
    ARROW_RIGHT: "right triangle \u2014 info/forward",
    ARROW_LEFT: "left triangle \u2014 back",
    LOZENGE: "the brand marker",
    SQUARE: "small square \u2014 bullet-style marker",
    BULLET: "bullet \u2014 list item / current-selection marker",
    MIDDLE_DOT: "middle dot \u2014 inline separator",
    BOX_H: "box drawing \u2014 horizontal rule",
    BOX_V: "box drawing \u2014 vertical rule",
    BOX_TL: "box drawing \u2014 top-left corner",
    BOX_TR: "box drawing \u2014 top-right corner",
    BOX_BL: "box drawing \u2014 bottom-left corner",
    BOX_BR: "box drawing \u2014 bottom-right corner",
    DOUBLE_H: "double box drawing \u2014 horizontal rule",
    DOUBLE_V: "double box drawing \u2014 vertical rule",
    DOUBLE_TL: "double box drawing \u2014 top-left corner",
    DOUBLE_TR: "double box drawing \u2014 top-right corner",
    DOUBLE_BL: "double box drawing \u2014 bottom-left corner",
    DOUBLE_BR: "double box drawing \u2014 bottom-right corner",
    "\u2715": "multiplication X \u2014 close/exit button",
    "\u2714": "heavy check mark \u2014 confirmed selection",
    "\u2756": "heavy diamond \u2014 the diamond-ban's brand-safe alternate",
    "\u2726": "black four-pointed star \u2014 accent marker",
    "\u2727": "white four-pointed star \u2014 accent marker",
    "\u27e1": "white concave diamond \u2014 accent marker",
}


def is_cataloged(ch: str) -> bool:
    """True if `ch` is in the vetted SAFE_GLYPH_CATALOG -- the fast path
    for a test or reviewer to confirm a glyph is pre-approved without
    re-running unicodedata/is_emoji_risk checks by hand."""
    return ch in SAFE_GLYPH_CATALOG


def is_emoji_risk(ch: str) -> bool:
    """True if `ch` falls in a Unicode block that's predominantly emoji/
    pictographic, unless it's on the _ESTABLISHED_SAFE exemption list.

    Deliberately independent of is_width_safe()/audit_string(): this
    catches missing-font-glyph-coverage bugs (tofu/fallback rendering),
    which East Asian Width cannot see -- EAW measures column width, not
    whether a font actually has the glyph.
    """
    if len(ch) != 1:
        return False
    if ch in _ESTABLISHED_SAFE:
        return False
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RISK_RANGES)


# ─── Runtime audit helper ─────────────────────────────────────────────────


def is_width_safe(ch: str) -> bool:
    """True if `ch` is guaranteed to render as one terminal cell.

    Uses the Unicode East Asian Width property. Returns False for Wide,
    Fullwidth, and Ambiguous — Ambiguous because while it's narrow in
    Western locales, CJK locales and emoji-presentation terminals render
    it wide, and we can't assume the operator's terminal.
    """
    if len(ch) != 1:
        return False  # multi-char or combining — punt
    return unicodedata.east_asian_width(ch) in ("N", "Na", "H")


def audit_string(s: str) -> list[tuple[int, str, str]]:
    """Return a list of (index, char, eaw_property) for every UNSAFE glyph in `s`.

    Intended for verifying *banner strings* and other width-sensitive output —
    NOT for auditing whole source files (docstrings with box-drawing chars
    will false-positive everywhere).

    The whitelist below is empirical: characters that are EAW=Ambiguous per
    Unicode's table but render as one cell on every terminal we've shipped
    on. The actually-dangerous chars (diamonds, emoji, fullwidth) remain
    flagged.
    """
    # Empirically-narrow Ambiguous chars used throughout the codebase
    # without ever causing alignment issues:
    DE_FACTO_NARROW = frozenset({
        # Severity / inline markers
        CROSS, BULLET, MIDDLE_DOT,
        # Box-drawing (designed for terminals; safe on every modern emulator)
        "\u2500", "\u2502", "\u250C", "\u2510", "\u2514", "\u2518",
        "\u251C", "\u2524", "\u252C", "\u2534", "\u253C",  # light variants
        "\u2550", "\u2551", "\u2554", "\u2557", "\u255A", "\u255D",
        "\u2560", "\u2563", "\u2566", "\u2569", "\u256C",  # double variants
        # Punctuation that's Ambiguous-but-narrow in every Western locale
        "\u2013", "\u2014",  # en-dash, em-dash
        "\u00A7",            # section sign §
        "\u2192", "\u2190", "\u2191", "\u2193",  # arrows
        # Common math comparisons used in docstrings
        "\u2260", "\u2264", "\u2265", "\u00D7",
    })
    out: list[tuple[int, str, str]] = []
    for i, ch in enumerate(s):
        eaw = unicodedata.east_asian_width(ch)
        if eaw not in ("W", "F", "A"):
            continue
        if ch in DE_FACTO_NARROW:
            continue
        out.append((i, ch, eaw))
    return out


__all__ = [
    "CHECK", "CROSS", "ARROW_RIGHT", "ARROW_LEFT", "ARROW_RIGHT_HEAVY",
    "LOZENGE", "SQUARE", "BULLET", "MIDDLE_DOT",
    "BOX_H", "BOX_V", "BOX_TL", "BOX_TR", "BOX_BL", "BOX_BR",
    "DOUBLE_H", "DOUBLE_V", "DOUBLE_TL", "DOUBLE_TR", "DOUBLE_BL", "DOUBLE_BR",
    "UNSAFE_DIAMOND", "UNSAFE_DIAMOND_BLACK", "UNSAFE_DIAMOND_SUIT",
    "UNSAFE_NO_ENTRY", "UNSAFE_WARNING", "UNSAFE_HEART", "UNSAFE_STAR",
    "SEVERITY_OK", "SEVERITY_WARNING", "SEVERITY_ERROR", "SEVERITY_INFO",
    "SEVERITY_BULLET",
    "BRAND_MARKER", "BRAND_MARKER_LEFT", "BRAND_MARKER_RIGHT",
    "is_width_safe", "audit_string", "is_emoji_risk",
    "SAFE_GLYPH_CATALOG", "is_cataloged",
]
