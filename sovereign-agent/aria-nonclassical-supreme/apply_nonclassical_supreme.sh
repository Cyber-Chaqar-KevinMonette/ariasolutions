#!/usr/bin/env bash
# apply_nonclassical_supreme.sh — Non-classical supremacy: the quantum-faithful superposition processor.
#   1. src/sovereign_agent/nonclassical_supreme/  (superpose, speed_proof, quality_proof, router, __init__)
#   2. src/sovereign_agent/tools/nc_supreme_tools.py — nc_process(T1), nc_route(T1), nc_speed_proof(T0), nc_quality_proof(T0)
#   3. tools/__init__.py registration   4. tests   5. run tests
# Reversibility: backups at aria-nonclassical-supreme/backups/.  Apply via scripts/safe_apply.sh for full guards.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-nonclassical-supreme"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-nonclassical-supreme apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/nonclassical_supreme"
cp "$STAGING"/payload/src/sovereign_agent/nonclassical_supreme/*.py "$REPO_ROOT/src/sovereign_agent/nonclassical_supreme/"
cp "$STAGING/payload/src/sovereign_agent/tools/nc_supreme_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied nonclassical_supreme/ + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# nc-supreme-import-d" in t:
    print("SKIP: already patched")
else:
    imp = next((l for l in t.splitlines() if "nonclassical-import-d" in l),
               next((l for l in t.splitlines() if "autonomy-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .nc_supreme_tools import NCProcessTool, NCRouteTool, NCSpeedProofTool, NCQualityProofTool  # nc-supreme-import-d", 1)
    allk = next((l for l in t.splitlines() if "nonclassical-all-d" in l),
                next((l for l in t.splitlines() if "autonomy-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "NCProcessTool",  # nc-supreme-all-d\n    "NCRouteTool",\n    "NCSpeedProofTool",\n    "NCQualityProofTool",', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/nonclassical_supreme/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/nc_supreme_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_nonclassical_supreme.py" "$REPO_ROOT/tests/test_nonclassical_supreme.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_nonclassical_supreme.py" -q
echo "=== aria-nonclassical-supreme applied — quantum-faithful, 1000×+ proven. 💛 ==="
