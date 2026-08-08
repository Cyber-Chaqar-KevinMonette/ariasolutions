"""patcher.py — re-fix the safe-glyphs regression, grounded against the
CURRENT live files (not the old, stale `aria-safe-glyphs/`, whose apply
script does a full-file replacement of `cockpit/app.py` from a ~half-sized
week-old payload and is confirmed dangerous to run — see that module's
own folder, left untouched).

The bug (real, live, confirmed via direct grep for the U+FE0F variation-
selector codepoint): glyphs like "⚠️" / "⏸️" / "▪️" are a base character
plus an invisible variation selector. Terminals disagree on their cell
width, the cursor desyncs from what's drawn, and the TUI layout visibly
corrupts. `aria-safe-glyphs/` fixed this once; Workstream O's full
rewrite of `requests.py` this session (the dual-inbox build) predates
that fix and reintroduced the exact same glyphs — `cockpit/app.py` is
still clean (confirmed), but `workflow/requests.py` and `cli.py` are not.

Fix, matching the original module's own mapping: deferred ⏸️ → 💤,
needs_attention ⚠️ → 🚩, priority "normal" ▪️ → empty (never shown, per
the original module's own note — kept as a dict key with value "",
NOT removed, since VALID_PRIORITY = frozenset(PRIORITY_EMOJI) depends on
"normal" staying a valid key).

`cli.py`'s occurrences are a SEPARATE hardcoded copy, not references to
requests.py's dict — both must be fixed independently.
"""
from __future__ import annotations

MARK = "safe-glyphs-regrounded-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# workflow/requests.py — the STATUS_EMOJI / PRIORITY_EMOJI dicts + banner
# ═══════════════════════════════════════════════════════════════════════

REQUESTS_BANNER_ANCHOR = (
    "║  deferred ⏸️ / revisit 🔖 / needs_attention ⚠️ — each carrying the context  ║\n"
)
REQUESTS_BANNER_NEW = (
    "║  deferred 💤 / revisit 🔖 / needs_attention 🚩 — each carrying the context  ║\n"
)

REQUESTS_STATUS_EMOJI_ANCHOR = (
    'STATUS_EMOJI = {\n'
    '    "open": "🟡", "answered": "🟢", "resolved": "✅", "cancelled": "⚪",\n'
    '    "deferred": "⏸️", "needs_attention": "⚠️", "revisit": "🔖",\n'
    '}\n'
)
REQUESTS_STATUS_EMOJI_NEW = (
    'STATUS_EMOJI = {\n'
    '    "open": "🟡", "answered": "🟢", "resolved": "✅", "cancelled": "⚪",\n'
    f'    "deferred": "💤", "needs_attention": "🚩", "revisit": "🔖",  # {MARK}\n'
    '}\n'
)

REQUESTS_PRIORITY_EMOJI_ANCHOR = (
    'PRIORITY_EMOJI = {\n'
    '    "low": "🔽", "normal": "▪️", "high": "🔼", "urgent": "🔴",\n'
    '}\n'
)
REQUESTS_PRIORITY_EMOJI_NEW = (
    'PRIORITY_EMOJI = {\n'
    f'    "low": "🔽", "normal": "", "high": "🔼", "urgent": "🔴",  # {MARK}\n'
    '}\n'
)

REQUESTS_DEFER_DOCSTRING_ANCHOR = (
    '        """Set aside for now, optionally with why + when to come back. ⏸️"""\n'
)
REQUESTS_DEFER_DOCSTRING_NEW = (
    f'        """Set aside for now, optionally with why + when to come back. 💤"""  # {MARK}\n'
)

REQUESTS_FLAG_DOCSTRING_ANCHOR = (
    '        """Flag as needing more attention, optionally with why. ⚠️"""\n'
)
REQUESTS_FLAG_DOCSTRING_NEW = (
    f'        """Flag as needing more attention, optionally with why. 🚩"""  # {MARK}\n'
)


def patch_requests(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, REQUESTS_BANNER_ANCHOR, REQUESTS_BANNER_NEW, label="requests banner anchor")
    text = _replace_once(
        text, REQUESTS_STATUS_EMOJI_ANCHOR, REQUESTS_STATUS_EMOJI_NEW, label="STATUS_EMOJI anchor"
    )
    text = _replace_once(
        text, REQUESTS_PRIORITY_EMOJI_ANCHOR, REQUESTS_PRIORITY_EMOJI_NEW, label="PRIORITY_EMOJI anchor"
    )
    text = _replace_once(
        text, REQUESTS_DEFER_DOCSTRING_ANCHOR, REQUESTS_DEFER_DOCSTRING_NEW,
        label="requests defer docstring anchor",
    )
    text = _replace_once(
        text, REQUESTS_FLAG_DOCSTRING_ANCHOR, REQUESTS_FLAG_DOCSTRING_NEW,
        label="requests flag docstring anchor",
    )
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# cli.py — 5 hardcoded occurrences, independent of requests.py's dict
# ═══════════════════════════════════════════════════════════════════════

CLI_DEFER_DOCSTRING_ANCHOR = '    """Set a request aside for now — with why + when. ⏸️"""\n'
CLI_DEFER_DOCSTRING_NEW = f'    """Set a request aside for now — with why + when. 💤"""  # {MARK}\n'

CLI_DEFER_PRINT_ANCHOR = (
    '    _print(f"⏸️  deferred [{r.short_id}]" + (f" — when: {when}" if when else ""))\n'
)
CLI_DEFER_PRINT_NEW = (
    f'    _print(f"💤 deferred [{{r.short_id}}]" + (f" — when: {{when}}" if when else ""))  # {MARK}\n'
)

CLI_FLAG_DOCSTRING_ANCHOR = '    """Flag a request as needing more attention. ⚠️"""\n'
CLI_FLAG_DOCSTRING_NEW = f'    """Flag a request as needing more attention. 🚩"""  # {MARK}\n'

CLI_FLAG_PRINT_ANCHOR = '    _print(f"⚠️  flagged [{r.short_id}] — needs more attention")\n'
CLI_FLAG_PRINT_NEW = f'    _print(f"🚩 flagged [{{r.short_id}}] — needs more attention")  # {MARK}\n'

CLI_PARKED_DOCSTRING_ANCHOR = (
    '    """Everything set aside to revisit — deferred ⏸️, revisit 🔖, flagged ⚠️.\n'
)
CLI_PARKED_DOCSTRING_NEW = (
    f'    """Everything set aside to revisit — deferred 💤, revisit 🔖, flagged 🚩.  # {MARK}\n'
)


def patch_cli(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(
        text, CLI_DEFER_DOCSTRING_ANCHOR, CLI_DEFER_DOCSTRING_NEW, label="cli defer docstring anchor"
    )
    text = _replace_once(
        text, CLI_DEFER_PRINT_ANCHOR, CLI_DEFER_PRINT_NEW, label="cli defer print anchor"
    )
    text = _replace_once(
        text, CLI_FLAG_DOCSTRING_ANCHOR, CLI_FLAG_DOCSTRING_NEW, label="cli flag docstring anchor"
    )
    text = _replace_once(
        text, CLI_FLAG_PRINT_ANCHOR, CLI_FLAG_PRINT_NEW, label="cli flag print anchor"
    )
    text = _replace_once(
        text, CLI_PARKED_DOCSTRING_ANCHOR, CLI_PARKED_DOCSTRING_NEW, label="cli parked docstring anchor"
    )
    return text, True
