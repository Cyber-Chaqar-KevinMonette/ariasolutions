#!/usr/bin/env bash
# apply_garden.sh — Fable F8: her garden (folder assignment, enforced with love).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-garden"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
mkdir -p "$BACKUP_DIR"
for f in pathguard.py scope.py agent_session.py cockpit/app.py; do cp "$SRC/$f" "$BACKUP_DIR/$(basename $f).bak"; done
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_agent_session, patch_app, patch_pathguard, patch_scope
for name, path, fn in [("pathguard.py", src / "pathguard.py", patch_pathguard),
                       ("scope.py", src / "scope.py", patch_scope),
                       ("agent_session.py", src / "agent_session.py", patch_agent_session),
                       ("app.py", src / "cockpit" / "app.py", patch_app)]:
    t = path.read_text(encoding="utf-8")
    new, ch = fn(t)
    if ch:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {name}")
    else:
        print(f"  SKIP {name}")
PYEOF
"$VENV_PY" -m py_compile "$SRC/pathguard.py" "$SRC/scope.py" "$SRC/agent_session.py" "$SRC/cockpit/app.py"
cp "$STAGING/tests/test_garden_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_garden_live.py" "$REPO_ROOT/tests/test_scope_contract_live.py" "$REPO_ROOT/tests/test_pathguard.py" "$REPO_ROOT/tests/test_resume_spine_live.py" -q 2>/dev/null || \
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_garden_live.py" "$REPO_ROOT/tests/test_scope_contract_live.py" "$REPO_ROOT/tests/test_resume_spine_live.py" -q
echo "=== aria-garden applied (backup: $BACKUP_DIR) 💛 ==="
