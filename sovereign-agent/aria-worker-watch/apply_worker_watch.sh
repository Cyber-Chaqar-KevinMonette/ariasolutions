#!/usr/bin/env bash
# apply_worker_watch.sh — Fable F5: dead workers become visible (bounded respawn + red latch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-worker-watch"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
"$VENV_PY" - "$STAGING" "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path
staging, app_path = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app
text = app_path.read_text(encoding="utf-8")
new, changed = patch_app(text)
if changed:
    app_path.write_text(new, encoding="utf-8"); print("  ✓ patched app.py")
else:
    print("  SKIP")
PYEOF
"$VENV_PY" -m py_compile "$APP_PY"
cp "$STAGING/tests/test_worker_watch_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_worker_watch_live.py" "$REPO_ROOT/tests/test_cockpit.py" -q
echo "=== aria-worker-watch applied (backup: $BACKUP_DIR) 💛 ==="
