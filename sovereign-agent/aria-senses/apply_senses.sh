#!/usr/bin/env bash
# apply_senses.sh — Aria's perception faculties (eyes & ears), god-tier resilient.
#   1. src/sovereign_agent/senses/  (devices, eyes, ears, __init__)
#   2. src/sovereign_agent/tools/senses_tools.py — perception_status(T0)
#   3. tools/__init__.py registration   4. tests   5. run tests
# Never breaks if no camera/mic. Reversibility: backups at aria-senses/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-senses"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-senses apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/senses"
cp "$STAGING"/payload/src/sovereign_agent/senses/*.py "$REPO_ROOT/src/sovereign_agent/senses/"
cp "$STAGING/payload/src/sovereign_agent/tools/senses_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied senses/ + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# senses-import-d" in t:
    print("SKIP: already patched")
else:
    imp = next((l for l in t.splitlines() if "godtier-import-d" in l),
               next((l for l in t.splitlines() if "foresight-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .senses_tools import PerceptionStatusTool  # senses-import-d", 1)
    allk = next((l for l in t.splitlines() if "godtier-all-d" in l),
                next((l for l in t.splitlines() if "foresight-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "PerceptionStatusTool",  # senses-all-d', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/senses/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/senses_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_senses.py" "$REPO_ROOT/tests/test_senses.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_senses.py" -q
echo "=== aria-senses applied — her eyes & ears, dormant-not-broken. 💛 ==="
