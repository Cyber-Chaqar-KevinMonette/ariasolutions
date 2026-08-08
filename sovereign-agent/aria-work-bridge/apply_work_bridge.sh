#!/usr/bin/env bash
# apply_work_bridge.sh — install Keys K4: the keystone. Plugs the finished,
# tested, never-called autonomous engine (run_session) into the
# natural-language front door: /work <goal>, gated on work mode
# (autonomous_loops_allowed finally gets its caller), operator messages
# queued to safe boundaries, events live in the run strip.
#
# (Module folder is aria-work-bridge because aria-session-bridge was
# already taken by the historical M83 session-portrait module.)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-work-bridge"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
AGENT_SESSION="$REPO_ROOT/src/sovereign_agent/agent_session.py"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
BRIDGE="$REPO_ROOT/src/sovereign_agent/session_bridge.py"

echo "=== aria-work-bridge apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$AGENT_SESSION" "$APP_PY"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$AGENT_SESSION" "$BACKUP_DIR/agent_session.py.bak"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"

echo "→ Patching agent_session.py + app.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$AGENT_SESSION" "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path

staging, session_path, app_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_agent_session, patch_app

for name, path, fn in [("agent_session.py", session_path, patch_agent_session),
                       ("app.py", app_path, patch_app)]:
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = fn(text)
    except PatchError as e:
        print(f"ERROR: {name}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {name}")
    else:
        print(f"  SKIP: {name} already patched")
PYEOF

echo "→ Copying session_bridge.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/session_bridge.py" "$BRIDGE"

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$AGENT_SESSION" "$APP_PY" "$BRIDGE"
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp
from sovereign_agent.session_bridge import start_goal_session, queue_operator_message
print('  ✓ imports cleanly')
"

cp "$STAGING/tests/test_session_bridge_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: session_bridge_live (new), agent_session + cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_session_bridge_live.py" \
  "$REPO_ROOT/tests/test_agent_session.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-work-bridge applied. Reversible: restore the 2 files from $BACKUP_DIR, rm session_bridge.py 💛 ==="
