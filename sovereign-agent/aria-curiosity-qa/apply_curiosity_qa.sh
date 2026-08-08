#!/usr/bin/env bash
# apply_curiosity_qa.sh — install Keys K6: her wonder, observable.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-curiosity-qa"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
CURIOSITY="$REPO_ROOT/src/sovereign_agent/curiosity.py"

echo "=== aria-curiosity-qa apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
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

echo "→ Copying curiosity.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/curiosity.py" "$CURIOSITY"

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$APP_PY" "$CURIOSITY"
"$VENV_PY" -c "from sovereign_agent.cockpit import CockpitApp; from sovereign_agent.curiosity import wonder; print('  ✓ imports cleanly')"

cp "$STAGING/tests/test_curiosity_qa_live.py" "$REPO_ROOT/tests/"
echo "Running: curiosity_qa_live (new) + cockpit + run_surface (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_curiosity_qa_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  "$REPO_ROOT/tests/test_run_surface_live.py" \
  -q

echo "=== aria-curiosity-qa applied. Reversible: restore app.py from $BACKUP_DIR, rm curiosity.py 💛 ==="
