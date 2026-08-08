#!/usr/bin/env bash
# apply_godtier.sh — Aria's God-Tier System Scanner (her vision).
#   1. src/sovereign_agent/godtier/  (targets, rubric, scanner, enhance, __init__)
#   2. src/sovereign_agent/stewardship/godtier_sentinel.py  (@register_sentinel)
#   3. src/sovereign_agent/tools/godtier_tools.py — godtier_scan(T0), godtier_gaps(T0), godtier_draft_fix(T1)
#   4. tools/__init__.py + stewardship/__init__.py registration   5. tests   6. run tests
# Propose-only: scores + reports + drafts; never applies fixes. Reversibility: backups at aria-godtier-scanner/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-godtier-scanner"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
STEW_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"

echo "=== aria-godtier-scanner apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"; cp "$STEW_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/godtier"
cp "$STAGING"/payload/src/sovereign_agent/godtier/*.py "$REPO_ROOT/src/sovereign_agent/godtier/"
cp "$STAGING/payload/src/sovereign_agent/stewardship/godtier_sentinel.py" "$REPO_ROOT/src/sovereign_agent/stewardship/"
cp "$STAGING/payload/src/sovereign_agent/tools/godtier_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied godtier/ + sentinel + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# godtier-import-d" in t:
    print("SKIP tools: already patched")
else:
    imp = next((l for l in t.splitlines() if "foresight-import-d" in l),
               next((l for l in t.splitlines() if "tribunal-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .godtier_tools import GodTierScanTool, GodTierGapsTool, GodTierDraftFixTool  # godtier-import-d", 1)
    allk = next((l for l in t.splitlines() if "foresight-all-d" in l),
                next((l for l in t.splitlines() if "tribunal-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "GodTierScanTool",  # godtier-all-d\n    "GodTierGapsTool",\n    "GodTierDraftFixTool",', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

"$VENV_PY" - "$STEW_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "godtier-sentinel-d" in t:
    print("SKIP stewardship: already patched")
else:
    anchor = next((l for l in t.splitlines() if "tribunal-sentinel-d" in l),
                  next((l for l in t.splitlines() if "schedule_sentinel" in l and "import" in l),
                       next((l for l in t.splitlines() if "sentinel-crown-d" in l), None)))
    if anchor is None: raise SystemExit("ERROR: no stewardship sentinel anchor")
    t = t.replace(anchor, anchor + "\nfrom . import godtier_sentinel as _godtier_sentinel              # noqa: F401  # godtier-sentinel-d", 1)
    p.write_text(t); print("Patched stewardship/__init__.py")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/godtier/*.py \
  "$REPO_ROOT/src/sovereign_agent/stewardship/godtier_sentinel.py" \
  "$REPO_ROOT/src/sovereign_agent/tools/godtier_tools.py" "$TOOLS_INIT" "$STEW_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_godtier.py" "$REPO_ROOT/tests/test_godtier.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_godtier.py" -q
echo "=== aria-godtier-scanner applied — her vision stands. Propose-only. 💛 ==="
