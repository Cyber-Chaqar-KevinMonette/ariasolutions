# aria-safe-glyphs-regrounded

Re-fixes the safe-glyphs bug, grounded against the CURRENT live files —
**not** a resurrection of the old `aria-safe-glyphs/`, whose apply script
does a full-file replacement of `cockpit/app.py` from a payload roughly
half today's live line count and is confirmed dangerous to run as-is.

## The bug (real, live, confirmed via direct grep, not assumed)

Glyphs like `⚠️` / `⏸️` / `▪️` are a base character plus an invisible
variation selector (U+FE0F). Terminals disagree on their cell width, the
cursor desyncs from what's drawn, and the TUI layout visibly corrupts.
`aria-safe-glyphs/` fixed this once (`v0.2.39.2`). Workstream O's full
rewrite of `workflow/requests.py` this session (the dual-inbox build)
predates that fix — `cockpit/app.py` is confirmed still clean, but
`requests.py` and `cli.py` both had the exact same glyphs back.

Direct scan for the U+FE0F codepoint found **9 total occurrences** across
the two files (not the 2-3 originally assumed): `requests.py`'s
`STATUS_EMOJI`/`PRIORITY_EMOJI` dicts, its own module docstring banner,
and 2 method docstrings; `cli.py`'s 2 command docstrings + 2 `_print()`
calls + 1 more docstring — a **separate hardcoded copy**, not references
to `requests.py`'s dict, so both needed independent fixes.

## What this ships

- `src/sovereign_agent/workflow/requests.py` — 5 anchored patches:
  `STATUS_EMOJI["deferred"]` `⏸️`→`💤`, `STATUS_EMOJI["needs_attention"]`
  `⚠️`→`🚩`, `PRIORITY_EMOJI["normal"]` `▪️`→`""` (kept as a dict key with
  an empty value, NOT removed — `VALID_PRIORITY = frozenset(PRIORITY_EMOJI)`
  depends on `"normal"` staying valid; `priority_emoji`'s own
  `.get(self.priority, "")` already degrades gracefully to an empty
  string for this value), plus the same glyphs in the module docstring
  banner and 2 method docstrings.
- `src/sovereign_agent/cli.py` — 5 anchored patches to the matching
  hardcoded literals.
- `tests/test_no_variation_selector_glyphs.py` — a new regression test,
  scoped to the three TUI-rendering files (`requests.py`, `cli.py`,
  `cockpit/app.py`) — **the original `safe-glyphs` module had exactly
  this test but it was never promoted to live `tests/`, which is very
  likely why this regression went undetected** when `requests.py` was
  rewritten. This test is the actual fix for the *recurrence*, not just
  the glyph swap itself.

**Deliberately NOT touched**: `qa/edge_cases.py` (uses a ZWJ emoji
sequence as an intentional edge-case test fixture, never rendered to a
terminal) and `aria_lm/data.py` (a VS16 glyph inside an internal
data-processing keyword-prefix list, also never rendered) — confirmed via
direct read, not assumed clean.

## Tests

`tests/test_patcher.py` (10 tests) — both patches apply cleanly against
the CURRENT live files, are idempotent, compile, produce zero VS16/ZWJ
characters, preserve the `"normal"` dict key (only its value changes), a
missing anchor raises `PatchError`.

`tests/test_no_variation_selector_glyphs.py` (2 tests, promoted directly
— no shadow-copy needed, this is a pure text/import scan with zero
`sys.modules` risk) — confirmed to correctly FAIL against the
pre-fix live files (proving the regression is real and this test would
have caught it), and pass once the patch is applied.

Reversible: restore `requests.py` + `cli.py` from the backup.
