#!/usr/bin/env bash
# apply_scope_contract.sh — install Keys K10: her ability to SCOPE.
# Pre-registered honesty at the boundary of work: /work "<goal> | scope: ..."
# declares the contract; guidance carries it; out-of-scope NEXT_SUBTASK
# proposals are held for review; drift is visible before the budget wall.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-scope-contract"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
BRIDGE="$REPO_ROOT/src/sovereign_agent/session_bridge.py"
AGENT_SESSION="$REPO_ROOT/src/sovereign_agent/agent_session.py"
SURFACE="$REPO_ROOT/src/sovereign_agent/cockpit/run_surface.py"
SCOPE="$REPO_ROOT/src/sovereign_agent/scope.py"

echo "=== aria-scope-contract apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$BRIDGE" "$BACKUP_DIR/session_bridge.py.bak"
cp "$AGENT_SESSION" "$BACKUP_DIR/agent_session.py.bak"
cp "$SURFACE" "$BACKUP_DIR/run_surface.py.bak"

echo "→ Patching (3 files, anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$BRIDGE" "$AGENT_SESSION" "$SURFACE" <<'PYEOF'
import sys
from pathlib import Path

staging, bridge_p, session_p, surface_p = (Path(a) for a in sys.argv[1:5])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_agent_session, patch_bridge, patch_run_surface

for name, path, fn in [("session_bridge.py", bridge_p, patch_bridge),
                       ("agent_session.py", session_p, patch_agent_session),
                       ("run_surface.py", surface_p, patch_run_surface)]:
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

echo "→ Copying scope.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/scope.py" "$SCOPE"

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$BRIDGE" "$AGENT_SESSION" "$SURFACE" "$SCOPE"
"$VENV_PY" -c "
from sovereign_agent.scope import ScopeContract, parse_goal_with_scope
from sovereign_agent.cockpit import CockpitApp
print('  ✓ imports cleanly')
"

cp "$STAGING/tests/test_scope_contract_live.py" "$REPO_ROOT/tests/"
echo "Running: scope_contract_live (new) + session bridge + agent_session (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_scope_contract_live.py" \
  "$REPO_ROOT/tests/test_session_bridge_live.py" \
  "$REPO_ROOT/tests/test_agent_session.py" \
  -q

echo "=== aria-scope-contract applied. Reversible: restore the 3 files from $BACKUP_DIR, rm scope.py 💛 ==="
