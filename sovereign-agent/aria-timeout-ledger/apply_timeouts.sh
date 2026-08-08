#!/usr/bin/env bash
# apply_timeouts.sh — Timeout round T1: the persisted timeout ledger.
# guard → copy payload (new package, nothing to back up) → py_compile →
# copy tests → run tests. Reversible: backups under
# aria-timeout-ledger/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-timeout-ledger"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== aria-timeout-ledger apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

mkdir -p "$REPO_ROOT/src/sovereign_agent/timeouts"
cp "$STAGING"/payload/src/sovereign_agent/timeouts/*.py "$REPO_ROOT/src/sovereign_agent/timeouts/"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/timeouts/*.py

cp "$STAGING/tests/test_timeouts.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_timeouts.py" -q

echo "=== aria-timeout-ledger applied. Reversible: backups at $BACKUP_DIR 💛 ==="
