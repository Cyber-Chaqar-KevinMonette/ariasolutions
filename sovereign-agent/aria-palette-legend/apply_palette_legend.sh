#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_palette_legend.sh — palette descriptions, 4 new buttons, a legend
#  (v0.2.39.0). Idempotent. BUILDS ON aria-inbox-context.tar.gz.
#
#  Changes (full-file replacement of cockpit/app.py; backup written):
#    • every palette button now has a one-line description
#    • hover a button → tooltip showing its command + what it does
#    • `/palette` (also /buttons, /legend) prints the full legend to chat
#    • F1 help explains hovering + /palette
#    • 4 new buttons: inbox · parked · caps · vault  (read-only/safe)
#    • palette grows to 3 balanced rows
#    • cockpit safety: vault MUTATIONS (init/encrypt/decrypt/rotate) stay
#      guarded; only `vault status`/`verify` are click-safe
#    • tests updated (palette size cap → 3 rows; new palette tests)
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
# guard: inbox-context bundle must be applied (the enriched pane calls
# requests.context_lines(), which only exists after that bundle)
if ! grep -q 'def context_lines' "$PKG/workflow/requests.py" 2>/dev/null \
   || ! grep -q 'id="inbox-log"' "$PKG/cockpit/app.py" 2>/dev/null; then
  echo "✗ this builds on aria-inbox-context.tar.gz (rich inbox context + the"
  echo "  4th pane). Apply that first, then re-run this."
  exit 1
fi
ts(){ date +%Y%m%d%H%M%S; }
[[ -f "$PKG/cockpit/app.py" ]] && cp "$PKG/cockpit/app.py" "$PKG/cockpit/app.py.bak.$(ts)"
cp "$PAYLOAD/src/sovereign_agent/cockpit/app.py" "$PKG/cockpit/app.py"
echo "  ✓ cockpit/app.py (backup written as app.py.bak.<ts>)"
cp "$PAYLOAD/tests/test_cockpit.py"      "$ROOT/tests/test_cockpit.py"
cp "$PAYLOAD/tests/test_v_0_2_31_0.py"   "$ROOT/tests/test_v_0_2_31_0.py"
echo "  ✓ tests/test_cockpit.py  tests/test_v_0_2_31_0.py"
echo "→ compile check"
python3 -m py_compile "$PKG/cockpit/app.py" "$ROOT/tests/test_cockpit.py" "$ROOT/tests/test_v_0_2_31_0.py"
echo "  ✓ compiles"
echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest -q          # expect: 1615 passed, 1 skipped"
echo "    sov cockpit        # hover any button to read what it does;"
echo "                       # type /palette for the full legend"
