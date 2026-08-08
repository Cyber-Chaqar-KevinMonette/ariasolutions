#!/usr/bin/env bash
# apply_autonomy.sh — Supervised Autonomy Sessions (time-boxed, observable, resumable, bounded).
#   1. src/sovereign_agent/autonomy/  (session, plan_forge, __init__)
#   2. src/sovereign_agent/tools/autonomy_tools.py — autonomy_plan(T1), autonomy_propose(T1),
#      autonomy_status(T0), autonomy_pause(T1)
#   3. tools/__init__.py registration   4. tests   5. run tests
# Bounded blast-radius (staged drafting/verify/scrutiny only; never outward/sealed/apply); always-stoppable.
# Reversibility: backups at aria-autonomy-session/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-autonomy-session"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-autonomy-session apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/autonomy"
cp "$STAGING"/payload/src/sovereign_agent/autonomy/*.py "$REPO_ROOT/src/sovereign_agent/autonomy/"
cp "$STAGING/payload/src/sovereign_agent/tools/autonomy_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied autonomy/ + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# autonomy-import-d" in t:
    print("SKIP: already patched")
else:
    imp = next((l for l in t.splitlines() if "senses-import-d" in l),
               next((l for l in t.splitlines() if "godtier-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .autonomy_tools import AutonomyPlanTool, AutonomyProposeTool, AutonomyStatusTool, AutonomyPauseTool  # autonomy-import-d", 1)
    allk = next((l for l in t.splitlines() if "senses-all-d" in l),
                next((l for l in t.splitlines() if "godtier-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "AutonomyPlanTool",  # autonomy-all-d\n    "AutonomyProposeTool",\n    "AutonomyStatusTool",\n    "AutonomyPauseTool",', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/autonomy/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/autonomy_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_autonomy.py" "$REPO_ROOT/tests/test_autonomy.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_autonomy.py" -q
echo "=== aria-autonomy-session applied — bounded, observable, resumable autonomy. 💛 ==="
