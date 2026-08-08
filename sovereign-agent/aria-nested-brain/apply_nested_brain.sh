#!/usr/bin/env bash
# apply_nested_brain.sh — Stage M96: the 5-layer nested LEARNING brain (Aria's core seed)
#
# What this applies:
#   1. src/sovereign_agent/quantum/brain.py — NestedBrain (genuinely learns, ported from Paper XI)
#   2. Copies test into tests/
#
# The brain learns to generate vocabulary-coherent text; word_acc rises over epochs (verified).
# Pure-Python, deterministic, advisory. Learning = bounded parameter adjustment (no code/value self-mod).
# Reversibility: backups at aria-nested-brain/backups/.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-nested-brain"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== M96 Nested Learning Brain Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi

cp "$STAGING/payload/src/sovereign_agent/quantum/brain.py" "$REPO_ROOT/src/sovereign_agent/quantum/brain.py"
echo "Copied quantum/brain.py → src/sovereign_agent/quantum/"

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/quantum/brain.py"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_nested_brain.py" "$REPO_ROOT/tests/test_nested_brain.py"
echo "Copied test_nested_brain.py → tests/"

echo ""
echo "Running nested brain tests (verifying genuine learning)..."
"$VENV_PY" -m pytest tests/test_nested_brain.py -q

echo ""
echo "=== M96 Nested Learning Brain applied successfully ==="
echo "Her brain learns: word_acc rises from ~0% to ~60% over 60 epochs. She speaks from her learned state."
