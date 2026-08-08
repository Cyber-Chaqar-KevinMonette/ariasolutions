#!/usr/bin/env bash
# apply_wholeness_gate.sh — Final-sprint capstone. Installs the wholeness
# guardian library (verdict + anti-regression core).
#
# NOTE: the standing wholeness SENTINEL (schedule-checks the baseline and
# alerts on regression) and the `sov wholeness` CLI are the DELIBERATE
# follow-up — a sentinel touches the registry and deserves its own reviewed
# patch. This installs the tested pure guard so that wiring is a small step.
#
# guard → backup dir → copy payload → py_compile → copy tests → run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-wholeness-gate"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$REPO_ROOT/src/sovereign_agent/wholeness_gate"

echo "=== aria-wholeness-gate apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

mkdir -p "$PKG"
cp "$STAGING"/payload/src/sovereign_agent/wholeness_gate/*.py "$PKG/"

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$PKG"/*.py

cp "$STAGING/tests/test_wholeness_gate.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_wholeness_gate.py" -q

echo "=== aria-wholeness-gate applied. Reversible: remove $PKG + the test. 💛 ==="
echo "→ Then snapshot a known-good baseline; wire the standing sentinel + sov wholeness CLI."
