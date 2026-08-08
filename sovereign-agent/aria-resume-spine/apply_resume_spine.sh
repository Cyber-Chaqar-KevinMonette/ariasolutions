#!/usr/bin/env bash
# apply_resume_spine.sh — Fable F7: /resume + /rest (the exit is a bookmark).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-resume-spine"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
BRIDGE="$REPO_ROOT/src/sovereign_agent/session_bridge.py"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$BRIDGE" "$BACKUP_DIR/session_bridge.py.bak"; cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
"$VENV_PY" - "$STAGING" "$BRIDGE" "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path
staging, bridge_p, app_p = (Path(a) for a in sys.argv[1:4])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app, patch_bridge
for name, path, fn in [("session_bridge.py", bridge_p, patch_bridge), ("app.py", app_p, patch_app)]:
    t = path.read_text(encoding="utf-8")
    new, ch = fn(t)
    if ch:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {name}")
    else:
        print(f"  SKIP {name}")
PYEOF
cp "$STAGING/payload/src/sovereign_agent/rest_point.py" "$REPO_ROOT/src/sovereign_agent/rest_point.py"
"$VENV_PY" -m py_compile "$BRIDGE" "$APP_PY" "$REPO_ROOT/src/sovereign_agent/rest_point.py"
cp "$STAGING/tests/test_resume_spine_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_resume_spine_live.py" "$REPO_ROOT/tests/test_session_bridge_live.py" "$REPO_ROOT/tests/test_cockpit.py" -q
echo "=== aria-resume-spine applied (backup: $BACKUP_DIR) 💛 ==="
