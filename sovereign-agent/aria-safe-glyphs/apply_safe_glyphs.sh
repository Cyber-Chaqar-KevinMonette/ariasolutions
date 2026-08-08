#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_safe_glyphs.sh — purge variation-selector glyphs that glitch the TUI
#  (v0.2.39.2). Idempotent. BUILDS ON aria-help-refbuttons.tar.gz.
#
#  The bug: glyphs like "⚠️" / "⏸️" / "▪️" are a base char + an invisible
#  variation selector (U+FE0F). Terminals disagree on their cell width, the
#  cursor desyncs from what's drawn, and the layout visibly corrupts.
#
#  The fix (full-file replacements; backups written as *.bak.<ts>):
#    • status glyphs:   deferred  ⏸️ → 💤      needs_attention ⚠️ → 🚩
#    • priority glyph:  normal    ▪️ → (none, it was never shown anyway)
#    • every request-command output + docstring + the palette description
#      updated to the safe glyphs
#    • NO variation selector (U+FE0F) or ZWJ (U+200D) remains in the TUI
#      glyph modules — enforced by new tests so it can't regress
#
#  Untouched on purpose: bare text-presentation marks (⚠ ● ○ ✓ ✗ ★ ◊ ♥) have
#  stable width and are an established convention — they are not the bug.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PAYLOAD="$HERE/payload"
ROOT="${1:-$PWD}"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"; while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }; d="$(dirname "$d")"; done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root or pass the path"; exit 1; }
echo "◊ repo root: $ROOT"
PKG="$ROOT/src/sovereign_agent"
# guard: help-refbuttons bundle must be applied (this builds on it)
if ! grep -q 'REFERENCE_BUTTONS' "$PKG/cockpit/app.py" 2>/dev/null; then
  echo "✗ this builds on aria-help-refbuttons.tar.gz (help-exit fix + the"
  echo "  right-side reference buttons). Apply that first, then re-run this."
  exit 1
fi
ts(){ date +%Y%m%d%H%M%S; }
bc(){ [[ -f "$2" ]] && cp "$2" "$2.bak.$(ts)"; cp "$PAYLOAD/$1" "$2"; }
bc "src/sovereign_agent/workflow/requests.py" "$PKG/workflow/requests.py"
bc "src/sovereign_agent/cli.py"               "$PKG/cli.py"
bc "src/sovereign_agent/cockpit/app.py"       "$PKG/cockpit/app.py"
echo "  ✓ requests.py  cli.py  app.py (backups as *.bak.<ts>)"
cp "$PAYLOAD/tests/test_cockpit.py" "$ROOT/tests/test_cockpit.py"
echo "  ✓ tests/test_cockpit.py"
echo "→ compile check"
python3 -m py_compile "$PKG/workflow/requests.py" "$PKG/cli.py" "$PKG/cockpit/app.py" "$ROOT/tests/test_cockpit.py"
echo "  ✓ compiles"
echo "→ verifying zero variation selectors / ZWJ in the TUI modules"
python3 - "$PKG" <<'PY'
import sys
pkg=sys.argv[1]
bad=0
for f in (f"{pkg}/workflow/requests.py", f"{pkg}/cockpit/app.py", f"{pkg}/cli.py"):
    s=open(f,encoding="utf-8").read()
    if "\uFE0F" in s or "\u200D" in s:
        print("  ✗ still has VS/ZWJ:", f); bad=1
print("  ✓ clean" if not bad else "  ✗ NOT clean")
sys.exit(bad)
PY
echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest -q          # expect: 1625 passed, 1 skipped"
echo "    sov cockpit        # the warning/pause glyphs no longer glitch the layout"
