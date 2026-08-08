#!/usr/bin/env bash
# apply_cockpit_guard.sh — Stage M86: cockpit framework-collision regression guard
#
# What this applies:
#   1. tests/test_cockpit_guard.py — AST guard: no cockpit Textual subclass may
#      assign to a reserved MessagePump/Widget attribute (e.g. _running).
#
# Test-only module: no src/ changes. Codifies the 2026-06-22 close-button bug fix
# so it can never be reintroduced.
#
# Reversibility: removes tests/test_cockpit_guard.py to undo.
# Prerequisites: run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-cockpit-guard"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== M86 Cockpit Guard Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo ""

if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

mkdir -p "$REPO_ROOT/tests"
cp "$STAGING/tests/test_cockpit_guard.py" "$REPO_ROOT/tests/test_cockpit_guard.py"
echo "Copied test_cockpit_guard.py → tests/"

echo ""
echo "Running cockpit guard tests..."
"$VENV_PY" -m pytest tests/test_cockpit_guard.py -v

echo ""
echo "=== M86 Cockpit Guard applied successfully ==="
