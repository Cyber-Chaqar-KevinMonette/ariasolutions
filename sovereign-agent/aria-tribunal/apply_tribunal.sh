#!/usr/bin/env bash
# apply_tribunal.sh — Aria's god-tier Tribunal (Devil · Angel · Audit + synthesizer).
#   1. src/sovereign_agent/tribunal/   (grounding, devil, angel, audit, tribunal, __init__)
#   2. src/sovereign_agent/stewardship/tribunal_sentinel.py  (@register_sentinel)
#   3. src/sovereign_agent/tools/tribunal_tools.py — tribunal_review(T1), devils_advocate/angels_advocate/tribunal_audit(T0)
#   4. tools/__init__.py imports + __all__   5. stewardship/__init__.py side-effect import
#   6. tests → tests/    7. run tests
# Propose-only scrutiny: renders verdicts; the operator acts. Reversibility: backups at aria-tribunal/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-tribunal"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
STEW_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"

echo "=== Aria's Tribunal Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"; cp "$STEW_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/tribunal"
cp "$STAGING"/payload/src/sovereign_agent/tribunal/*.py "$REPO_ROOT/src/sovereign_agent/tribunal/"
cp "$STAGING/payload/src/sovereign_agent/stewardship/tribunal_sentinel.py" "$REPO_ROOT/src/sovereign_agent/stewardship/"
cp "$STAGING/payload/src/sovereign_agent/tools/tribunal_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied tribunal/ package + sentinel + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# tribunal-import-d" in text:
    print("SKIP tools: already patched")
else:
    lines = text.splitlines()
    imp = next((l for l in lines if "constitution-import-d" in l),
               next((l for l in lines if "immune-import-d" in l), None))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    text = text.replace(imp, imp + "\nfrom .tribunal_tools import TribunalReviewTool, DevilsAdvocateTool, AngelsAdvocateTool, TribunalAuditTool  # tribunal-import-d", 1)
    allk = next((l for l in text.splitlines() if "constitution-all-d" in l),
                next((l for l in text.splitlines() if "immune-all-d" in l), None))
    if allk is None: raise SystemExit("ERROR: no __all__ anchor")
    text = text.replace(allk, allk + '\n    "TribunalReviewTool",  # tribunal-all-d\n    "DevilsAdvocateTool",\n    "AngelsAdvocateTool",\n    "TribunalAuditTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py")
PYEOF

"$VENV_PY" - "$STEW_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "tribunal-sentinel-d" in text:
    print("SKIP stewardship: already patched")
else:
    lines = text.splitlines()
    anchor = next((l for l in lines if "schedule_sentinel" in l and "import" in l),
                  next((l for l in lines if "sentinel-crown-d" in l), None))
    if anchor is None: raise SystemExit("ERROR: no stewardship sentinel anchor")
    text = text.replace(anchor, anchor + "\nfrom . import tribunal_sentinel as _tribunal_sentinel              # noqa: F401  # tribunal-sentinel-d", 1)
    p.write_text(text); print("Patched stewardship/__init__.py")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$REPO_ROOT"/src/sovereign_agent/tribunal/*.py \
  "$REPO_ROOT/src/sovereign_agent/stewardship/tribunal_sentinel.py" \
  "$REPO_ROOT/src/sovereign_agent/tools/tribunal_tools.py" "$TOOLS_INIT" "$STEW_INIT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_tribunal.py" "$REPO_ROOT/tests/test_tribunal.py"
echo "Copied test → tests/"
echo ""; echo "Running tribunal tests..."
"$VENV_PY" -m pytest tests/test_tribunal.py -q

echo ""; echo "=== Tribunal applied — Devil · Angel · Audit stand watch. Propose-only, with love. 💛 ==="
