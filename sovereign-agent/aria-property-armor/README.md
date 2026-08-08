# aria-property-armor

Hypothesis finally lands — Gym round #10. `hypothesis>=6.100` had been in
`pyproject.toml` (twice) with **zero imports anywhere** since it was added.

## What it fuzzes

Bounded property tests (`max_examples≈50`, `deadline=None`) over the
scanner/parser surfaces — the code whose whole job is handling inputs
nobody hand-wrote:

- `path_scan.scanner.scan_text` — never raises on arbitrary unicode;
  findings well-formed; `allow_test_refs=True` is monotonic (can only
  remove findings, never create them).
- `scanner_tier_a` text scanners (secrets, bare-except, mutable-defaults,
  authority-tier-drift, all-exports) — never raise.
- `glyph_sentinel._classify` — total over unicode: every char gets exactly
  one classification, never an exception.
- `aria_lm.data.clean_prose` — never raises; idempotent
  (`clean(clean(x)) == clean(x)`).
- `prompt_diet.split_sections` — byte-identical round-trip over synthetic
  templates (this round's own new parser gets fuzzed too).

## The catch (first fuzz pass, within seconds)

`scan_all_exports(":")` raised an unhandled `SyntaxError` — the one
AST-based tier-a scanner had no parse guard, so a corrupted or mid-edit
`tools/__init__.py` would crash the scanner instead of being reported.
Fixed as a small direct live edit (`scanner_tier_a/scanner.py`):
unparseable input now returns a block-severity
`anchor-integrity/unparseable` finding — loud, never a crash. The exact
argument for property testing, demonstrated by the module that introduces
it.

## Verify / Apply

```
.venv/bin/python -m pytest aria-property-armor/tests/ -q
./aria-property-armor/apply_property_armor.sh
```

Reversible: `rm tests/test_property_armor_live.py`.
