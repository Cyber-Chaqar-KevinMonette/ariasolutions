# ⚠ SUPERSEDED — DO NOT RUN THE APPLY SCRIPT

**Status (2026-07-04, gym-round triage):** this module's intent (purging
glitch-causing variation-selector/ZWJ glyphs) was fully re-implemented and
applied to live on 2026-07-03 by **`aria-safe-glyphs-regrounded/`**, built
against the CURRENT `requests.py`/`cli.py` with a promoted regression test
(`tests/test_no_variation_selector_glyphs.py`).

**Why this one must never be applied as-is:** its apply script does a
**full-file replacement of `cockpit/app.py` from a ~2,800-line payload** —
roughly HALF the current live file. Running it would silently destroy every
cockpit workstream applied since (M/N/O/P/security-strip-wire/paste-plus/
atelier/vessel-health/command-menu and more) — the exact failure shape of
the P0 regression (commit `8fc7267`) this project already had to recover
from once.

Kept as provenance only. If glyph work is ever needed again, extend
`aria-safe-glyphs-regrounded/` or the live `GlyphSentinel`
(`stewardship/glyph_sentinel.py`), not this folder.
