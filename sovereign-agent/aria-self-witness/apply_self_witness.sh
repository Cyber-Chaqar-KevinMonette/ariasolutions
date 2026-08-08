#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-self-witness"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
cp "$STAGING/payload/src/sovereign_agent/self_witness.py" "$REPO_ROOT/src/sovereign_agent/self_witness.py"
"$VENV_PY" - "$STAGING" "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path
staging, p = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import patch_app
t = p.read_text(encoding="utf-8")
new, ch = patch_app(t)
if ch:
    p.write_text(new, encoding="utf-8"); print("  ✓ app.py")
else:
    print("  SKIP")
PYEOF
"$VENV_PY" -m py_compile "$APP_PY" "$REPO_ROOT/src/sovereign_agent/self_witness.py"
cp "$STAGING/tests/test_self_witness_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_self_witness_live.py" "$REPO_ROOT/tests/test_cockpit.py" -q
echo "=== aria-self-witness applied (backup: $BACKUP_DIR) 💛 ==="
