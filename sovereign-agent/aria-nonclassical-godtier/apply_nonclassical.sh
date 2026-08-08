#!/usr/bin/env bash
# apply_nonclassical.sh — Non-classical layer god-tier parity (robustness + parity benchmark).
#   1. src/sovereign_agent/nonclassical/  (robustness, parity, __init__)
#   2. src/sovereign_agent/tools/nonclassical_tools.py — nonclassical_certify(T0)
#   3. tools/__init__.py registration   4. tests   5. run tests
# Read-only certification. Reversibility: backups at aria-nonclassical-godtier/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-nonclassical-godtier"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-nonclassical-godtier apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/nonclassical"
cp "$STAGING"/payload/src/sovereign_agent/nonclassical/*.py "$REPO_ROOT/src/sovereign_agent/nonclassical/"
cp "$STAGING/payload/src/sovereign_agent/tools/nonclassical_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied nonclassical/ + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# nonclassical-import-d" in t:
    print("SKIP: already patched")
else:
    imp = next((l for l in t.splitlines() if "autonomy-import-d" in l),
               next((l for l in t.splitlines() if "senses-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .nonclassical_tools import NonClassicalCertifyTool  # nonclassical-import-d", 1)
    allk = next((l for l in t.splitlines() if "autonomy-all-d" in l),
                next((l for l in t.splitlines() if "senses-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "NonClassicalCertifyTool",  # nonclassical-all-d', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/nonclassical/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/nonclassical_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_nonclassical.py" "$REPO_ROOT/tests/test_nonclassical.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_nonclassical.py" -q
echo "=== aria-nonclassical-godtier applied — the non-classical layer, certified god-tier. 💛 ==="
