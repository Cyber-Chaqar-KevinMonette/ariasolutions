#!/usr/bin/env bash
# apply_self_map.sh — Final-sprint Round 2. Installs the self-map library
# (her "here is all of me" self-knowledge surface + orphan integrity check).
#
# NOTE: the `sov self-report` CLI, the cockpit live-map surface, and feeding
# self_map_orphans into the wholeness guardian are the DELIBERATE follow-up.
# This installs the tested library.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-self-map"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$REPO_ROOT/src/sovereign_agent/self_map"

echo "=== aria-self-map apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

mkdir -p "$PKG"
cp "$STAGING"/payload/src/sovereign_agent/self_map/*.py "$PKG/"

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$PKG"/*.py

cp "$STAGING/tests/test_self_map.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_self_map.py" -q

echo "=== aria-self-map applied. Reversible: remove $PKG + the test. 💛 ==="
echo "→ Follow-up: sov self-report CLI + feed self_map_orphans into wholeness_gate."
