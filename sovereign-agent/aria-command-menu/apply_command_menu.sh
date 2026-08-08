#!/usr/bin/env bash
# apply_command_menu.sh — install Workstream M: command palette → scrollable
# popup menu + observability/security/emotions strips + missing-button audit.
#
# Ships:
#   - src/sovereign_agent/cockpit/app.py — 10 anchored, idempotent patches
#     (import, binding, action, compose(), CSS, on_mount timer,
#     on_button_pressed auto-close, 3 new refresh methods, 3 new palette
#     buttons found by the gap-audit, 1 allowlist fix). NOT a full-file
#     replace — this file is 4,894 lines and evolves fast.
#   - src/sovereign_agent/cockpit/command_palette_screen.py — NEW file: the
#     ModalScreen popup (mirrors ApplyQueueScreen's proven shape).
#
# Anatomy: guard (cockpit stopped + venv) → backup app.py → patch (anchored,
# idempotent, py_compile-verified) → copy new screen file → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-command-menu"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
SCREEN="$REPO_ROOT/src/sovereign_agent/cockpit/command_palette_screen.py"

echo "=== aria-command-menu apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP" ]] || { echo "ERROR: $APP not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (10 anchored edits, idempotent)..."
"$VENV_PY" - "$STAGING" "$APP" <<'PYEOF'
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

echo "→ Copying command_palette_screen.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/cockpit/command_palette_screen.py" "$SCREEN"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$APP" "$SCREEN"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp
from sovereign_agent.cockpit.app import CommandPaletteScreen
print('  ✓ imports cleanly (cockpit, CommandPaletteScreen)')
"

cp "$STAGING/tests/test_command_menu.py" "$REPO_ROOT/tests/"
echo "Running test suites: command_menu (new), cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_command_menu.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-command-menu applied. Reversible: restore app.py from $BACKUP_DIR and rm command_palette_screen.py 💛 ==="
