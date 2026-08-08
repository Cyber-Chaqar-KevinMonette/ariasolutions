#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_inbox_context.sh — rich context + scheduling for the inbox (v0.2.38.0)
#  Idempotent. BUILDS ON aria-inbox-pane.tar.gz (which builds on collab-secure).
#
#  Changes (full-file replacements; backups written as *.bak.<ts>):
#    • workflow/requests.py  rich context (why/when/priority/estimate/tags),
#                            multiple tags, parked/due/next, safe DB migration
#    • cli.py                `sov requests` gains: context flags on ask/defer/
#                            revisit/flag, next, parked, due, reopen, prompt-answer
#    • cockpit/app.py        inbox pane renders priority + why/when/tags + due
#    • tests/test_requests.py
#
#  Your existing human_requests table is migrated automatically (ADD COLUMN)
#  the first time anything opens it — existing requests are preserved.
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
# guard: inbox-pane bundle must be applied
if ! grep -q 'id="inbox-log"' "$PKG/cockpit/app.py" 2>/dev/null; then
  echo "✗ this builds on aria-inbox-pane.tar.gz (the 4th cockpit pane), which"
  echo "  doesn't look applied. Apply that first, then re-run this."
  exit 1
fi
ts(){ date +%Y%m%d%H%M%S; }
bc(){ [[ -f "$2" ]] && cp "$2" "$2.bak.$(ts)"; cp "$PAYLOAD/$1" "$2"; }
echo "→ updating requests + cli + cockpit (backups as *.bak.<ts>)"
bc "src/sovereign_agent/workflow/requests.py" "$PKG/workflow/requests.py"
bc "src/sovereign_agent/cli.py"               "$PKG/cli.py"
bc "src/sovereign_agent/cockpit/app.py"       "$PKG/cockpit/app.py"
echo "  ✓ requests.py  cli.py  app.py"
cp "$PAYLOAD/tests/test_requests.py" "$ROOT/tests/test_requests.py"; echo "  ✓ tests/test_requests.py"
echo "→ compile check"
python3 -m py_compile "$PKG/workflow/requests.py" "$PKG/cli.py" "$PKG/cockpit/app.py" "$ROOT/tests/test_requests.py"
echo "  ✓ all files compile"
echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest -q                  # expect: 1612 passed, 1 skipped"
echo "    sov requests ask \"Benchmark the tokenizer\" --kind research --why \"...\" --when \"phase 2\" --priority high --tag perf --tag parser"
echo "    sov requests          # open queue, with context"
echo "    sov requests next     # the single most pressing item"
echo "    sov requests parked   # everything to revisit (defer/revisit/flag)"
echo "    sov requests due      # parked items whose time has come"
echo "    sov requests reopen <id>"
echo "    sov cockpit           # the ◊ inbox pane now shows priority + why/when/tags"
