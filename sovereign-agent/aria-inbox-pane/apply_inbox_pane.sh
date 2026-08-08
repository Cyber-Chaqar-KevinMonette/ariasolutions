#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_inbox_pane.sh — add the ◊ inbox as a 4th cockpit pane  (v0.2.37.0)
#  Idempotent (plain file copies). BUILDS ON aria-collab-secure.tar.gz —
#  apply that one first if you haven't.
#
#  Changes:
#    • cockpit/app.py        + ◊ inbox pane (4th window), CSS, refresh worker
#    • workflow/requests.py  + statuses: deferred ⏸️ / needs_attention ⚠️ /
#                              revisit 🔖  (plus defer/flag/revisit/reopen)
#    • cli.py                + `sov requests defer|flag|revisit`
#    • tests                 + inbox-pane test, status tests, extended doctrine
#
#  These are full-file replacements of files whose base matches your tree.
#  A timestamped backup of each replaced file is written first, so nothing
#  is lost and you can diff if you want.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$HERE/payload"

# ── locate repo root ────────────────────────────────────────────────────────
ROOT="${1:-$PWD}"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    if [[ -f "$d/src/sovereign_agent/cli.py" ]]; then ROOT="$d"; break; fi
    d="$(dirname "$d")"
  done
fi
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  echo "✗ could not find src/sovereign_agent/cli.py."
  echo "  run from your sovereign-agent repo root, or: bash apply_inbox_pane.sh /path/to/repo"
  exit 1
fi
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"

# ── guard: the prior bundle must be applied ─────────────────────────────────
if [[ ! -f "$PKG/workflow/requests.py" ]] || ! grep -q 'name="vault"' "$PKG/cli.py"; then
  echo "✗ this drop builds on aria-collab-secure.tar.gz, which doesn't look applied."
  echo "  apply that bundle first (it adds requests.py, the vault, and the CLI groups),"
  echo "  then re-run this script."
  exit 1
fi

ts() { date +%Y%m%d%H%M%S; }
backup_and_copy() {  # $1 = src in payload (relative), $2 = dest absolute
  local src="$PAYLOAD/$1" dest="$2"
  if [[ -f "$dest" ]]; then cp "$dest" "$dest.bak.$(ts)"; fi
  cp "$src" "$dest"
}

echo "→ updating cockpit + requests + cli (backups written as *.bak.<ts>)"
backup_and_copy "src/sovereign_agent/cockpit/app.py"       "$PKG/cockpit/app.py"
backup_and_copy "src/sovereign_agent/workflow/requests.py" "$PKG/workflow/requests.py"
backup_and_copy "src/sovereign_agent/cli.py"               "$PKG/cli.py"
echo "  ✓ app.py  requests.py  cli.py"

echo "→ updating tests"
cp "$PAYLOAD/tests/test_cockpit.py"     "$ROOT/tests/test_cockpit.py"
cp "$PAYLOAD/tests/test_mos_surface.py" "$ROOT/tests/test_mos_surface.py"
cp "$PAYLOAD/tests/test_requests.py"    "$ROOT/tests/test_requests.py"
echo "  ✓ test_cockpit.py  test_mos_surface.py  test_requests.py"

echo "→ compile check"
python3 -m py_compile \
  "$PKG/cockpit/app.py" "$PKG/workflow/requests.py" "$PKG/cli.py" \
  "$ROOT/tests/test_cockpit.py" "$ROOT/tests/test_mos_surface.py" \
  "$ROOT/tests/test_requests.py"
echo "  ✓ all files compile"

echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest -q                  # expect: 1601 passed, 1 skipped"
echo "    sov cockpit                # the 4th pane ◊ inbox is now on the right"
echo
echo "  try the new states:"
echo "    sov requests ask \"Scan the new parser files\" --kind scan_files"
echo "    sov requests defer  <id>   # ⏸️  set aside"
echo "    sov requests flag   <id>   # ⚠️  needs attention"
echo "    sov requests revisit <id>  # 🔖 come back after more development"
