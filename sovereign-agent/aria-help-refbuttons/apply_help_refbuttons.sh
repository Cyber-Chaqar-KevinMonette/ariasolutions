#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_help_refbuttons.sh — help-screen exit fix + right-side reference
#  buttons (v0.2.39.1). Idempotent. BUILDS ON aria-palette-legend.tar.gz.
#
#  Two fixes (full-file replacement of cockpit/app.py; backup written):
#    1) HELP SCREEN WOULD NOT CLOSE. Root cause: F1 re-opened help on top of
#       itself (stacking). Now:
#         • F1 TOGGLES (open → F1 closes, no more stacking)
#         • Esc and q close it (with an on_key fallback so a flaky terminal
#           Escape can't trap you)
#         • a clickable ✕ Close button (no keyboard needed)
#         • the help body now scrolls for long content
#    2) RIGHT-SIDE REFERENCE BUTTONS. The last palette row now shows the
#       `sov` command buttons on the LEFT and two reference buttons on the
#       RIGHT: [legend] (prints what every button does) and [? help] (opens
#       the overlay). They run in-cockpit actions, not subprocess commands,
#       so the palette-safety invariant is untouched.
#    + tests for every exit path and the new buttons.
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
# guard: palette-legend bundle must be applied (this builds on it)
if ! grep -q 'def _show_palette_legend' "$PKG/cockpit/app.py" 2>/dev/null; then
  echo "✗ this builds on aria-palette-legend.tar.gz (button descriptions +"
  echo "  the /palette legend). Apply that first, then re-run this."
  exit 1
fi
ts(){ date +%Y%m%d%H%M%S; }
[[ -f "$PKG/cockpit/app.py" ]] && cp "$PKG/cockpit/app.py" "$PKG/cockpit/app.py.bak.$(ts)"
cp "$PAYLOAD/src/sovereign_agent/cockpit/app.py" "$PKG/cockpit/app.py"
echo "  ✓ cockpit/app.py (backup written as app.py.bak.<ts>)"
cp "$PAYLOAD/tests/test_cockpit.py" "$ROOT/tests/test_cockpit.py"
echo "  ✓ tests/test_cockpit.py"
echo "→ compile check"
python3 -m py_compile "$PKG/cockpit/app.py" "$ROOT/tests/test_cockpit.py"
echo "  ✓ compiles"
echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest -q          # expect: 1622 passed, 1 skipped"
echo "    sov cockpit"
echo "      • F1 (or the [? help] button) opens help; F1 / Esc / q / ✕ Close all exit"
echo "      • the [legend] button (bottom-right) prints what every button does"
