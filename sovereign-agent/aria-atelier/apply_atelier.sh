#!/usr/bin/env bash
# apply_atelier.sh — install Workstream A: "Aria's Atelier," a live work-
# theater pane streaming every file write/edit and every command she runs.
#
# Ships:
#   - src/sovereign_agent/work_events.py — NEW file: translates a tool's
#     raw execute() result into a richer work-write/work-edit/work-command
#     event, derived purely from data already in scope at the one tool-
#     dispatch choke point. No individual tool file is touched.
#   - src/sovereign_agent/loop.py — 2 anchored, idempotent patches (import
#     + one call at the existing "Invariant 2" record point).
#   - src/sovereign_agent/cockpit/app.py — 6 anchored, idempotent patches
#     (CSS pane + divider, compose() 5th pane, on_mount binding, a routing
#     branch added to the START of the EXISTING _render_event(), a new
#     _render_work_event() method). NOT a full-file replace.
#
# Anatomy: guard (cockpit stopped + venv) → backup loop.py + app.py → patch
# (anchored, idempotent, py_compile-verified) → copy work_events.py (new
# file) → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-atelier"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOOP="$REPO_ROOT/src/sovereign_agent/loop.py"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
WORK_EVENTS="$REPO_ROOT/src/sovereign_agent/work_events.py"

echo "=== aria-atelier apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$LOOP" ]] || { echo "ERROR: $LOOP not found."; exit 1; }
[[ -f "$APP" ]] || { echo "ERROR: $APP not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$LOOP" "$BACKUP_DIR/loop.py.bak"
cp "$APP" "$BACKUP_DIR/app.py.bak"

echo "→ Patching loop.py (2 anchored edits) + app.py (6 anchored edits), idempotent..."
"$VENV_PY" - "$STAGING" "$LOOP" "$APP" <<'PYEOF'
import sys
from pathlib import Path

staging, loop_path, app_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app, patch_loop

loop_text = loop_path.read_text(encoding="utf-8")
try:
    new_loop, changed = patch_loop(loop_text)
except PatchError as e:
    print(f"ERROR: loop.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed:
    loop_path.write_text(new_loop, encoding="utf-8")
    print("  ✓ patched loop.py")
else:
    print("  SKIP: loop.py already patched")

app_text = app_path.read_text(encoding="utf-8")
try:
    new_app, changed = patch_app(app_text)
except PatchError as e:
    print(f"ERROR: app.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed:
    app_path.write_text(new_app, encoding="utf-8")
    print("  ✓ patched app.py")
else:
    print("  SKIP: app.py already patched")
PYEOF

echo "→ Copying work_events.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/work_events.py" "$WORK_EVENTS"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$LOOP" "$APP" "$WORK_EVENTS"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp
from sovereign_agent import work_events
from sovereign_agent import loop as _loop
print('  ✓ imports cleanly (cockpit, work_events, loop)')
"

# NOTE: promote test_atelier_live.py, NOT test_atelier.py. The latter uses
# a shadow-copy-and-patch mechanism needed only for pre-apply verification;
# promoting it caused a real regression elsewhere this session (sys.modules
# save/delete/restore decoupling shared module-level state across tests) —
# see test_security_strip_wire.py's README for the full story. Keep the
# shadow-copy version staging-only.
cp "$STAGING/tests/test_atelier_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: atelier_live (new), cockpit + loop_utils (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_atelier_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  "$REPO_ROOT/tests/test_loop_utils.py" \
  -q

echo "=== aria-atelier applied. Reversible: restore loop.py + app.py from $BACKUP_DIR and rm work_events.py 💛 ==="
