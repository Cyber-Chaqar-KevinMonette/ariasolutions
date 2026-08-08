#!/usr/bin/env bash
# apply_cockpit_flush.sh — install Gym #5: nothing lost at shutdown.
#
# Two anchored patches to cockpit/app.py:
#   1. on_unmount: seals buffered ChunkRecorder turns (seal_now() had zero
#      shutdown callers — up to 20 turns lost per exit) + events.force_fsync()
#      (wired to loop/session exit but never to the cockpit's own exit).
#   2. The mid-turn conversation error handler surfaces probe_ollama's
#      reason_phrase for backend-shaped failures instead of an opaque
#      "conversation error".
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-cockpit-flush"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"

echo "=== aria-cockpit-flush apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP_PY" ]] || { echo "ERROR: $APP_PY not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (2 anchored edits, idempotent)..."
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

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$APP_PY"
"$VENV_PY" -c "from sovereign_agent.cockpit import CockpitApp; print('  ✓ cockpit imports cleanly')"

cp "$STAGING/tests/test_cockpit_flush_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: cockpit_flush_live (new), cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_cockpit_flush_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-cockpit-flush applied. Reversible: restore app.py from $BACKUP_DIR 💛 ==="
