#!/usr/bin/env bash
# apply_integrity.sh — Integrity round I1: the composite anti-misleading
# ledger. Composes 4 existing signals (grounding.gate, calibration.
# presumed_zombie_penalty, spectrum.lenses.witness, peig_sentinel's
# Identity score) that never cross-referenced each other before.
#
# guard (cockpit stopped + venv present) → copy payload (new package,
# nothing to back up) → py_compile → copy tests → run tests.
# Reversible: backups under aria-integrity-ledger/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-integrity-ledger"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== aria-integrity-ledger apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

# 1. copy payload package (new module, src/sovereign_agent/integrity/ doesn't exist yet)
mkdir -p "$REPO_ROOT/src/sovereign_agent/integrity"
cp "$STAGING"/payload/src/sovereign_agent/integrity/*.py "$REPO_ROOT/src/sovereign_agent/integrity/"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/integrity/*.py

# 2. promote + run tests
cp "$STAGING/tests/test_integrity.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_integrity.py" -q

echo "=== aria-integrity-ledger applied. Reversible: backups at $BACKUP_DIR 💛 ==="
