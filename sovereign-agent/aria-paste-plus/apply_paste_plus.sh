#!/usr/bin/env bash
# apply_paste_plus.sh — install Workstream B: right-click / long-text paste
# in the chat box.
#
# Ships:
#   - src/sovereign_agent/cockpit/app.py — 3 anchored, idempotent patches
#     (import PastePreviewScreen, RippleInput.on_mouse_down for right-click
#     paste, action_paste_clipboard rewritten to preview multi-line paste
#     instead of collapsing it + a new _send_pasted_text helper). NOT a
#     full-file replace — this file evolves fast.
#   - src/sovereign_agent/cockpit/paste_preview_screen.py — NEW file: the
#     ModalScreen popup (mirrors CommandPaletteScreen's proven shape).
#
# Anatomy: guard (cockpit stopped + venv) → backup app.py → patch (anchored,
# idempotent, py_compile-verified) → copy new screen file → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-paste-plus"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
SCREEN="$REPO_ROOT/src/sovereign_agent/cockpit/paste_preview_screen.py"

echo "=== aria-paste-plus apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP" ]] || { echo "ERROR: $APP not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (3 anchored edits, idempotent)..."
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

echo "→ Copying paste_preview_screen.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/cockpit/paste_preview_screen.py" "$SCREEN"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$APP" "$SCREEN"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp
from sovereign_agent.cockpit.app import PastePreviewScreen
print('  ✓ imports cleanly (cockpit, PastePreviewScreen)')
"

# NOTE: promote test_paste_plus_live.py, NOT test_paste_plus.py. The latter
# uses a shadow-copy-and-patch mechanism needed only for pre-apply
# verification; promoting it caused a real regression elsewhere this
# session (sys.modules save/delete/restore decoupling shared module-level
# state across tests) — see test_security_strip_wire.py's README for the
# full story. Keep the shadow-copy version staging-only.
cp "$STAGING/tests/test_paste_plus_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: paste_plus_live (new), cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_paste_plus_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-paste-plus applied. Reversible: restore app.py from $BACKUP_DIR and rm paste_preview_screen.py 💛 ==="
