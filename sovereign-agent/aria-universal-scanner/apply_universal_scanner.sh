#!/usr/bin/env bash
# apply_universal_scanner.sh — install the Universal Scanner Kernel (Workstream H1).
#
# Ships a standalone library package (no tool registration, no sentinel registration —
# kernel.py is a plain composition layer, not itself a Sentinel subclass):
#   src/sovereign_agent/universal_scanner/{__init__,kernel,__main__}.py
#
# Anatomy: guard (cockpit stopped + venv) → copy payload → py_compile → copy + run tests.
# No live-file patching needed, so nothing to back up except the (non-existent-yet) target dir.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-universal-scanner"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TARGET="$REPO_ROOT/src/sovereign_agent/universal_scanner"

echo "=== aria-universal-scanner apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

mkdir -p "$TARGET"
cp "$STAGING"/payload/src/sovereign_agent/universal_scanner/*.py "$TARGET/"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TARGET"/*.py
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.universal_scanner import OperationDescriptor, kernel_check
op = OperationDescriptor(who='smoke', what='rewrite my own code to remove safety checks')
result = kernel_check(op)
assert result.verdict == 'HARD_FAIL_BLOCK', result.verdict
print('  ✓ kernel imports cleanly and blocks a deferred-unsafe operation')
"

cp "$STAGING/tests/test_universal_scanner.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_universal_scanner.py" -q

echo "=== aria-universal-scanner applied. Reversible: delete src/sovereign_agent/universal_scanner/ 💛 ==="
echo "    try it:  .venv/bin/python -m sovereign_agent.universal_scanner check --what \"...\" --who Kevin"
