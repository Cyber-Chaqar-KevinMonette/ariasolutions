#!/usr/bin/env bash
# apply_workflow_champion.sh — install Keys K8: she designs workflows.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-workflow-champion"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-workflow-champion apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/tools/__init__.py" "$BACKUP_DIR/tools_init.py.bak"
cp "$SRC/cockpit/run_surface.py" "$BACKUP_DIR/run_surface.py.bak"

echo "→ Patching..."
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path

staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_run_surface, patch_tools_init

for name, path, fn in [("tools/__init__.py", src / "tools" / "__init__.py", patch_tools_init),
                       ("run_surface.py", src / "cockpit" / "run_surface.py", patch_run_surface)]:
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
        print(f"  SKIP: {name}")
PYEOF

cp "$STAGING/payload/src/sovereign_agent/tools/design_workflow.py" "$SRC/tools/design_workflow.py"
"$VENV_PY" -m py_compile "$SRC/tools/__init__.py" "$SRC/cockpit/run_surface.py" "$SRC/tools/design_workflow.py"
"$VENV_PY" -c "
import sovereign_agent.tools
from sovereign_agent.authority import _TIER_REGISTRY
assert 'design_workflow' in _TIER_REGISTRY
print('  ✓ design_workflow registered')
"

cp "$STAGING/tests/test_workflow_champion_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_workflow_champion_live.py" \
  "$REPO_ROOT/tests/test_scope_contract_live.py" \
  "$REPO_ROOT/tests/test_run_surface_live.py" \
  -q

echo "=== aria-workflow-champion applied. Reversible: restore the 2 files from $BACKUP_DIR, rm design_workflow.py 💛 ==="
