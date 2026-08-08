#!/usr/bin/env bash
# apply_scanner_tier_a.sh — install the Tier-A scanner harvest (Workstream J).
#
# Ships a standalone library package (no tool registration, no sentinel registration — these are
# plain scan functions, meant to be called directly or via H1's Universal Scanner Kernel fan-out):
#   src/sovereign_agent/scanner_tier_a/{__init__,scanner}.py
#
# Anatomy: guard (cockpit stopped + venv) → copy payload → py_compile → copy + run tests →
# self-scan live src/ to report real findings (same validation discipline as D).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-scanner-tier-a"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TARGET="$REPO_ROOT/src/sovereign_agent/scanner_tier_a"

echo "=== aria-scanner-tier-a apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

mkdir -p "$TARGET"
cp "$STAGING"/payload/src/sovereign_agent/scanner_tier_a/*.py "$TARGET/"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TARGET"/*.py
echo "  ✓ py_compile clean"

cp "$STAGING/tests/test_scanner_tier_a.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_scanner_tier_a.py" -q

echo "→ Self-scanning live src/ to report real findings..."
"$VENV_PY" -c "
from pathlib import Path
from sovereign_agent.scanner_tier_a import scan_tree, scan_anchor_integrity
result = scan_tree(Path('src/sovereign_agent'))
print(f'  {result.summary()}')
anchors = scan_anchor_integrity(Path('.'))
print(f'  {len(anchors)} dangling anchor(s) across all aria-*/ apply scripts')
"

echo "=== aria-scanner-tier-a applied. Reversible: delete src/sovereign_agent/scanner_tier_a/ 💛 ==="
