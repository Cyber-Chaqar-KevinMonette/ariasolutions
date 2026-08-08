#!/usr/bin/env bash
# apply_review_journal.sh — Final-sprint Round A (auto-mode transparency).
# Installs the review-journal library so every work session can leave a
# reviewable <data>/reviews/<session_id>/ directory + INDEX.md.
#
# NOTE: calling build_review() at session close-out (in session_bridge.py /
# agent_session.py) is a DELIBERATE follow-up, kept as its own reviewed
# patch since it touches the load-bearing session path. This script
# installs the tested library; a `sov reviews` CLI + the close-out hook
# land in the same round's follow-up step.
#
# guard → backup dir → copy payload → py_compile → copy tests → run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-review-journal"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$REPO_ROOT/src/sovereign_agent/review_journal"

echo "=== aria-review-journal apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

mkdir -p "$PKG"
cp "$STAGING"/payload/src/sovereign_agent/review_journal/*.py "$PKG/"

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$PKG"/*.py

cp "$STAGING/tests/test_review_journal.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_review_journal.py" -q

echo "=== aria-review-journal applied. Reversible: remove $PKG + the test. 💛 ==="
echo "→ Follow-up (deliberate): call build_review() at session close-out + add sov reviews CLI."
