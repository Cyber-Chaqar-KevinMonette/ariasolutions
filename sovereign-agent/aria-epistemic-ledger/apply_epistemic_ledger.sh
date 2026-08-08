#!/usr/bin/env bash
# apply_epistemic_ledger.sh — install the Epistemic organ (Workstream H3).
#
# Ships a standalone library package (no tool/sentinel registration — a plain
# ledger + registry, callable directly):
#   src/sovereign_agent/epistemic_ledger/{__init__,ledger}.py
#
# Anatomy: guard (cockpit stopped + venv) → copy payload → py_compile → copy + run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-epistemic-ledger"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TARGET="$REPO_ROOT/src/sovereign_agent/epistemic_ledger"

echo "=== aria-epistemic-ledger apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

mkdir -p "$TARGET"
cp "$STAGING"/payload/src/sovereign_agent/epistemic_ledger/*.py "$TARGET/"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TARGET"/*.py
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.epistemic_ledger import EpistemicLedger, UncertaintyRegistry
print('  ✓ imports cleanly:', EpistemicLedger, UncertaintyRegistry)
"

cp "$STAGING/tests/test_epistemic_ledger.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_epistemic_ledger.py" -q

echo "=== aria-epistemic-ledger applied. Reversible: delete src/sovereign_agent/epistemic_ledger/ 💛 ==="
