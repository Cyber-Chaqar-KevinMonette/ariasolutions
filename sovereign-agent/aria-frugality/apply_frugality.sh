#!/usr/bin/env bash
# apply_frugality.sh — Aria's god-tier hardware-reduction engine.
#   1. src/sovereign_agent/frugality/   (techniques catalog + VRAM planner)
#   2. src/sovereign_agent/tools/frugality_tools.py — frugality_catalog(T0), frugality_plan(T0)
#   3. tools/__init__.py imports + __all__    4. tests → tests/    5. run tests
#
# The headline lever — a real ternary BitNet b1.58 — ships WITH the aria_lm package
# (aria_lm/bitnet.py + the GPTConfig.ternary flag), applied via aria-own-mind/apply_own_mind.sh.
# This folder adds the catalog + planner + tools. Reversibility: backups at aria-frugality/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-frugality"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== Aria's Frugality Engine Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
if [[ ! -d "$REPO_ROOT/src/sovereign_agent/aria_lm" ]]; then
  echo "NOTE: aria_lm not in live src yet — the ternary BitNet ships with it (apply aria-own-mind to get BitNet)."
fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/frugality"
cp "$STAGING"/payload/src/sovereign_agent/frugality/*.py "$REPO_ROOT/src/sovereign_agent/frugality/"
cp "$STAGING/payload/src/sovereign_agent/tools/frugality_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied frugality/ package + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# frugality-import-d" in text:
    print("SKIP: already patched")
else:
    lines = text.splitlines()
    imp = next((l for l in lines if "tribunal-import-d" in l),
               next((l for l in lines if "constitution-import-d" in l),
                    next((l for l in lines if "immune-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    text = text.replace(imp, imp + "\nfrom .frugality_tools import FrugalityCatalogTool, FrugalityPlanTool  # frugality-import-d", 1)
    allk = next((l for l in text.splitlines() if "tribunal-all-d" in l),
                next((l for l in text.splitlines() if "constitution-all-d" in l),
                     next((l for l in text.splitlines() if "immune-all-d" in l), None)))
    if allk is None: raise SystemExit("ERROR: no __all__ anchor")
    text = text.replace(allk, allk + '\n    "FrugalityCatalogTool",  # frugality-all-d\n    "FrugalityPlanTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/frugality/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/frugality_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_frugality.py" "$REPO_ROOT/tests/test_frugality.py"
echo "Copied test → tests/"; echo ""; echo "Running frugality tests..."
"$VENV_PY" -m pytest tests/test_frugality.py -q

echo ""; echo "=== Frugality applied — our own BitNet + the honest 'how far we can go' planner. 💛 ==="
