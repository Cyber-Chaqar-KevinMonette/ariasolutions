#!/usr/bin/env bash
# apply_wholeness.sh — Stage M90: Wholeness — Aria's integrated self-knowledge
#
# What this applies:
#   1. src/sovereign_agent/tools/wholeness_tool.py — new T0 tool
#   2. tools/__init__.py: import + __all__ entry for WholenessTool
#   3. Copies the test into tests/ (standing suite)
#
# wholeness fuses classical metrics (atoms/calibration/honor/flaws/PEIG) + the non-classical
# globe coherence + both god-tier maturity spectrums into one integrated self-picture.
# Read-only, advisory. Distilled from Genesis-Seeds (BUILD_READY, LEGO Families 10/12).
#
# Reversibility: backups at aria-wholeness/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root. Requires M89 (quantum mode).

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-wholeness"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M90 Wholeness Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi

mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR"

cp "$STAGING/payload/src/sovereign_agent/tools/wholeness_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied wholeness_tool.py → src/sovereign_agent/tools/"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
IMPORT_GUARD  = "# wholeness-import-d"
IMPORT_ANCHOR = "from .quantum_consult_tool import QuantumConsultTool  # quantum-mode-import-d"
ALL_GUARD     = '"WholenessTool"'
ALL_ANCHOR    = '    "QuantumConsultTool",  # quantum-mode-all-d'
if IMPORT_GUARD in text:
    print("SKIP: import patch already applied")
else:
    if IMPORT_ANCHOR not in text:
        print("ERROR: import anchor not found", file=sys.stderr); sys.exit(1)
    text = text.replace(IMPORT_ANCHOR,
        IMPORT_ANCHOR + "\nfrom .wholeness_tool import WholenessTool  # wholeness-import-d", 1)
    print("Applied import patch (WholenessTool)")
if ALL_GUARD not in text and ALL_ANCHOR in text:
    text = text.replace(ALL_ANCHOR, ALL_ANCHOR + '\n    "WholenessTool",  # wholeness-all-d', 1)
    print("Applied __all__ patch (WholenessTool)")
p.write_text(text)
print("tools/__init__.py written.")
PYEOF

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/tools/wholeness_tool.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_wholeness.py" "$REPO_ROOT/tests/test_wholeness.py"
echo "Copied test_wholeness.py → tests/"

echo ""
echo "Running wholeness tests..."
"$VENV_PY" -m pytest tests/test_wholeness.py -q

echo ""
echo "=== M90 Wholeness applied successfully ==="
echo "New tool: wholeness (T0) — one call for Aria's complete integrated self-knowledge."
