#!/usr/bin/env bash
# apply_run_surface.sh — install Keys K1: payload-aware event rendering,
# red failures, the live run strip, and the mode/breaker status-bar fields.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-run-surface"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
RUN_SURFACE="$REPO_ROOT/src/sovereign_agent/cockpit/run_surface.py"

echo "=== aria-run-surface apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP_PY" ]] || { echo "ERROR: $APP_PY not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (7 anchored edits, idempotent)..."
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

echo "→ Copying run_surface.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/cockpit/run_surface.py" "$RUN_SURFACE"

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$APP_PY" "$RUN_SURFACE"
"$VENV_PY" -c "from sovereign_agent.cockpit import CockpitApp; print('  ✓ cockpit imports cleanly')"

cp "$STAGING/tests/test_run_surface_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: run_surface_live (new), cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_run_surface_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-run-surface applied. Reversible: restore app.py from $BACKUP_DIR, rm run_surface.py 💛 ==="
