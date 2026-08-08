"""osrs-flips patches — add the OSRS category, its 4 tier channels, and the
fetcher registration. Anchored + idempotent; refuses to guess."""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "osrs-flips-d"

# ── 1. source builder (verticals.py) ────────────────────────────────────
BUILDER_ANCHOR = '    return (f"wf-flip-{category}", category, "warframe-flip")\n'
BUILDER_INSERT = '''

def osrs_flip(tier: str) -> tuple[str, str, str]:
    """osrs-flips-d (Kevin, 2026-08-03): one source per CAPITAL TIER
    ("starter" | "mid" | "high" | "volume"). Tier is the axis that
    actually matters in OSRS — a new account cannot flip a Twisted Bow,
    and a whale does not care about a 600gp margin — so segmenting by
    bankroll is what makes the feed usable instead of taunting.
    `tier` rides in `url` as a marker, same convention as scrape() and
    warframe_flip()."""
    return (f"osrs-flip-{tier}", tier, "osrs-flip")
'''

# ── 2. the verticals (verticals.py) ─────────────────────────────────────
CATALOG_ANCHOR = "CATALOG: list[Vertical] = [\n"
CATALOG_INSERT = '''    # 🗡 OLD SCHOOL RUNESCAPE — osrs-flips-d (Kevin, 2026-08-03).
    # Grand Exchange flipping off the official wiki price API (no auth,
    # identifying UA per their policy). Channels split by capital tier,
    # not item type: that is the real constraint on a player.
    _v("osrs-starter", "OSRS: Starter Flips", "\\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("starter")],
       ["flip", "margin"],
       "Grand Exchange flips under 10k a unit — high ROI, small bankroll. "
       "Margins are AFTER the 1% GE tax, with buy limits and 24h volume.",
       price=700, channel="osrs-starter", excludes=[]),
    _v("osrs-mid", "OSRS: Mid Flips", "\\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("mid")],
       ["flip", "margin"],
       "Grand Exchange flips from 10k to 1M a unit, ranked by real profit "
       "per 4h buy-limit window.",
       price=700, channel="osrs-mid", excludes=[]),
    _v("osrs-high", "OSRS: High-Cap Flips", "\\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("high")],
       ["flip", "margin"],
       "Grand Exchange flips over 1M a unit — big margins, tight buy "
       "limits, so ranked on what you can actually clear per window.",
       price=700, channel="osrs-high", excludes=[]),
    _v("osrs-volume", "OSRS: High-Volume Flips", "\\U0001FA99", 0xC9A227, DEEP, "online",
       [osrs_flip("volume")],
       ["flip", "margin"],
       "The fastest-moving items on the GE — thin margins, but they fill "
       "immediately. Ranked by 24h volume.",
       price=700, channel="osrs-volume", excludes=[]),
'''

# ── 3. the category (verticals.py) ──────────────────────────────────────
CATEGORY_ANCHOR = '    "INCOME SECURING": ["business-grants"],\n'
CATEGORY_INSERT = ('    "OLD SCHOOL RUNESCAPE": ["osrs-starter", "osrs-mid", '
                   '"osrs-high",\n                             "osrs-volume"],\n')

# ── 4. the Discord category (blueprint.py) ──────────────────────────────
BLUEPRINT_ANCHOR = '''            CategorySpec("INCOME SECURING", read_only=True,
                         channels=_category_channels("INCOME SECURING")),
'''
BLUEPRINT_INSERT = '''            # osrs-flips-d (Kevin, 2026-08-03): GE flipping, split by
            # capital tier so a starter feed never buries someone in
            # Twisted Bow margins they can't touch.
            CategorySpec("OLD SCHOOL RUNESCAPE", read_only=True,
                         channels=_category_channels("OLD SCHOOL RUNESCAPE")),
'''

# ── 5. fetcher registration (fetchers.py) ───────────────────────────────
FETCHER_ANCHOR = '''    if kind == "warframe-flip":
        return WarframeFlipFetcher(opener=opener, on_outcome=on_outcome)
'''
FETCHER_INSERT = '''    if kind == "osrs-flip":
        # osrs-flips-d: official wiki price API, no auth, identifying UA.
        from sovereign_agent.osrs_flips.fetcher import OsrsFlipFetcher
        return OsrsFlipFetcher(opener=opener, on_outcome=on_outcome)
'''

# ── 3b. the /my-panel picker (verticals.py) ─────────────────────────────
# SUBSCRIBABLE_CATEGORIES is a SEPARATE tuple from CATEGORY_SLUGS. A
# category listed only in the latter gets real Discord channels but never
# appears in /my-panel, so nobody can subscribe to it. Missed on the first
# pass and caught live by Kevin — hence its own explicit step.
PANEL_ANCHOR = '    "INCOME SECURING",\n)\n'
PANEL_INSERT = ''  # handled as a replace, below — see apply()

PLAN = [
    ("verticals.py", BUILDER_ANCHOR, BUILDER_INSERT, "after"),
    ("verticals.py", CATALOG_ANCHOR, CATALOG_INSERT, "after"),
    ("verticals.py", CATEGORY_ANCHOR, CATEGORY_INSERT, "after"),
    ("verticals.py", PANEL_ANCHOR,
     '    "INCOME SECURING",\n    "OLD SCHOOL RUNESCAPE",\n)\n',
     "replace-tail"),
    ("discord_admin/blueprint.py", BLUEPRINT_ANCHOR, BLUEPRINT_INSERT, "after"),
    ("discord_runtime/fetchers.py", FETCHER_ANCHOR, FETCHER_INSERT, "after"),
]


def apply(src: Path) -> list[str]:
    out = []
    # verify every anchor across every file BEFORE writing anything, so a
    # bad anchor can't leave the tree half-patched
    texts: dict[str, str] = {}
    for rel, anchor, _ins, _pos in PLAN:
        t = texts.get(rel)
        if t is None:
            t = texts[rel] = (src / rel).read_text()
        if MARKER in t:
            continue
        if anchor not in t:
            raise ValueError(f"anchor not found in {rel}: {anchor[:60]!r}")

    for rel, anchor, ins, pos in PLAN:
        t = texts[rel]
        if ins.strip() and ins.strip()[:40] in t:
            out.append(f"{rel}: already patched")
            continue
        if pos == "replace-tail":
            # append INSIDE the closing paren, not after it
            texts[rel] = t.replace(anchor, ins, 1) if ins else t
        else:
            texts[rel] = t.replace(anchor, anchor + ins, 1)

    for rel, t in texts.items():
        (src / rel).write_text(t)
        out.append(f"{rel}: patched")
    return out


if __name__ == "__main__":
    try:
        for line in apply(Path(sys.argv[1])):
            print(line)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
