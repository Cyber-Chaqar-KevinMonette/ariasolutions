#!/usr/bin/env bash
# apply_security_strip_wire.sh — Workstream M follow-up: wire the security
# strip to J's real Tier-A scanner findings, now that J is live.
#
# Found during a plan-accuracy review: M's security strip was built with an
# "interim" design (authority tier census + a safe_eval presence check)
# because J's scanner_tier_a hadn't landed yet at the time — but J actually
# landed live (commit 78a5560) *before* M was built this same session, and
# M's implementation was never revisited. This closes that gap.
#
# Ships: src/sovereign_agent/cockpit/app.py — 4 anchored, idempotent patches
# (cache-attribute init, a 5-minute background-scan timer, a new thread
# worker running scan_tree() off the main thread, and a rewritten
# _refresh_security_strip that blends the cached scan counts into the
# existing tier census). NOT a full-file replace — same discipline as
# every other app.py patcher this session.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-security-strip-wire"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"

echo "=== aria-security-strip-wire apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP" ]] || { echo "ERROR: $APP not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (4 anchored edits, idempotent)..."
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

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$APP"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp
print('  ✓ imports cleanly')
"

# NOTE: promote test_security_strip_wire_live.py, NOT test_security_strip_wire.py.
# The latter uses a shadow-copy-and-patch mechanism needed only for pre-apply
# verification; promoting it to live tests/ caused a real regression (its
# sys.modules save/delete/restore dance decoupled shared module-level state
# across tests, breaking unrelated tests elsewhere in the suite — the same
# bug class already fixed once this session in test_locator_events_fix.py).
cp "$STAGING/tests/test_security_strip_wire_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: security_strip_wire_live (new), command_menu + cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_security_strip_wire_live.py" \
  "$REPO_ROOT/tests/test_command_menu.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-security-strip-wire applied. Reversible: restore app.py from $BACKUP_DIR 💛 ==="
