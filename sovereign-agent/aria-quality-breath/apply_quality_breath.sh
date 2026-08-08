#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-quality-breath"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
AS="$REPO_ROOT/src/sovereign_agent/agent_session.py"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$AS" "$BACKUP_DIR/agent_session.py.bak"
"$VENV_PY" - "$STAGING" "$AS" <<'PYEOF'
import sys
from pathlib import Path
staging, p = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import patch_agent_session
t = p.read_text(encoding="utf-8")
new, ch = patch_agent_session(t)
if ch:
    p.write_text(new, encoding="utf-8"); print("  ✓ agent_session.py")
else:
    print("  SKIP")
PYEOF
"$VENV_PY" -m py_compile "$AS"
cp "$STAGING/tests/test_quality_breath_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_quality_breath_live.py" "$REPO_ROOT/tests/test_scope_contract_live.py" "$REPO_ROOT/tests/test_resume_spine_live.py" "$REPO_ROOT/tests/test_agent_session.py" -q
echo "=== aria-quality-breath applied (backup: $BACKUP_DIR) 💛 ==="
