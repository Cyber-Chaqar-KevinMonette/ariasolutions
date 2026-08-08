#!/usr/bin/env bash
# apply_small_model_confidence.sh — Final-sprint Round 1 (companion to the
# small-model bridge). Installs the pure confidence/decision library.
#
# NOTE: wiring assess_turn() into the live /work session loop
# (agent_session.py) is a DELIBERATE follow-up, not done here — it touches
# the already-load-bearing run loop and deserves its own reviewed patch.
# This script installs the tested library so that wiring is a small,
# well-understood next step.
#
# guard → backup dir → copy payload → py_compile → copy tests → run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-small-model-confidence"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$REPO_ROOT/src/sovereign_agent/small_model_confidence"

echo "=== aria-small-model-confidence apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

# copy payload package (new package)
mkdir -p "$PKG"
cp "$STAGING"/payload/src/sovereign_agent/small_model_confidence/*.py "$PKG/"

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$PKG"/*.py

cp "$STAGING/tests/test_small_model_confidence.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_small_model_confidence.py" -q

echo "=== aria-small-model-confidence applied. Reversible: remove $PKG + the test. 💛 ==="
echo "→ Follow-up (deliberate): wire assess_turn() into agent_session.py's /work loop."
