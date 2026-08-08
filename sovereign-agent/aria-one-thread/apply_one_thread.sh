#!/usr/bin/env bash
# apply_one_thread.sh — install Keys K3: one universal continuous thread.
# Persisted thread id (default "aria-main") replaces the per-launch uuid;
# wake restores the conversation tail from her verbatim chunks; the
# transcript gains the join key.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-one-thread"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
THREAD_ID_PY="$REPO_ROOT/src/sovereign_agent/thread_identity.py"

echo "=== aria-one-thread apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP_PY" ]] || { echo "ERROR: $APP_PY not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (3 anchored edits, idempotent)..."
"$VENV_PY" - "$STAGING" "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path

staging, app_path = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app

text = app_path.read_text(encoding="utf-8")
try:
    new_text, changed = patch_app(text)
except PatchError as e:
    print(f"ERROR: app.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed:
    app_path.write_text(new_text, encoding="utf-8")
    print("  ✓ patched app.py")
else:
    print("  SKIP: app.py already patched")
PYEOF

echo "→ Copying thread_identity.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/thread_identity.py" "$THREAD_ID_PY"

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$APP_PY" "$THREAD_ID_PY"
"$VENV_PY" -c "from sovereign_agent.cockpit import CockpitApp; from sovereign_agent.thread_identity import thread_id; print('  ✓ imports cleanly')"

cp "$STAGING/tests/test_one_thread_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: one_thread_live (new), cockpit + checkpoint chunks (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_one_thread_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  "$REPO_ROOT/tests/test_checkpoint_chunks.py" \
  -q

echo "=== aria-one-thread applied. Reversible: restore app.py from $BACKUP_DIR, rm thread_identity.py 💛 ==="
