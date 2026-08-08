#!/usr/bin/env bash
# apply_timeout_chunked_tests.sh — Timeout round T5: the actual
# pytest-chunking fix.
# guard → backup → copy payload (run_tests_chunked.sh) → patch
# (.claude/PLAYBOOK.md doc sync) → bash-syntax check → tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-timeout-chunked-tests"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== aria-timeout-chunked-tests apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$REPO_ROOT/.claude/PLAYBOOK.md" "$BACKUP_DIR/PLAYBOOK.md.bak"

cp "$STAGING/payload/scripts/run_tests_chunked.sh" "$REPO_ROOT/scripts/"
chmod +x "$REPO_ROOT/scripts/run_tests_chunked.sh"

"$VENV_PY" - "$STAGING" "$REPO_ROOT" <<'PYEOF'
import sys
from pathlib import Path
staging, repo = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import DOC_PATCHES

for rel, fn in DOC_PATCHES.items():
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

echo "→ Bash-syntax check..."
bash -n "$REPO_ROOT/scripts/run_tests_chunked.sh"

cp "$STAGING/tests/test_run_tests_chunked.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_run_tests_chunked.py" -q

echo "=== aria-timeout-chunked-tests applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "→ Try it now: ./scripts/run_tests_chunked.sh"
