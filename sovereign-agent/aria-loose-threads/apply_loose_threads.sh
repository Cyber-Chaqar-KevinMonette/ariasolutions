#!/usr/bin/env bash
# apply_loose_threads.sh — Fable F1: the disconnection organ.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-loose-threads"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$SRC/stewardship/__init__.py" "$BACKUP_DIR/stewardship_init.py.bak"
mkdir -p "$SRC/loose_threads"
cp "$STAGING"/payload/src/sovereign_agent/loose_threads/*.py "$SRC/loose_threads/"
"$VENV_PY" - "$STAGING" "$SRC/stewardship/__init__.py" <<'PYEOF'
import sys
from pathlib import Path
staging, init_p = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import patch_stewardship_init
t = init_p.read_text(encoding="utf-8")
new, ch = patch_stewardship_init(t)
if ch:
    init_p.write_text(new, encoding="utf-8"); print("  ✓ stewardship/__init__.py")
else:
    print("  SKIP")
PYEOF
for f in "$SRC"/loose_threads/*.py; do "$VENV_PY" -m py_compile "$f"; done
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'loose-threads' in registry.registered_ids()
print('  ✓ loose-threads registered')"
cp "$STAGING/tests/test_loose_threads_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_loose_threads_live.py" "$REPO_ROOT/tests/test_sentinel_framework.py" -q
echo "=== aria-loose-threads applied (backup: $BACKUP_DIR) 💛 ==="
