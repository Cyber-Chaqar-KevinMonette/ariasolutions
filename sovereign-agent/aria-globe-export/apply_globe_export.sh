#!/usr/bin/env bash
# apply_globe_export.sh — Stage M95: Godot globe export (see her in 3D — Gen-5 seed)
#
# What this applies:
#   1. src/sovereign_agent/tools/globe_export_tool.py — quantum_globe_export (T1)
#   2. tools/__init__.py: import + __all__
#   3. Copies test into tests/
#
# Emits the 13-node globe as a 3D visualization payload (Godot/PEIG schema, Block 13.1). Requires M89.
# Reversibility: backups at aria-globe-export/backups/.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-globe-export"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M95 Globe Export Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi

mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$STAGING/payload/src/sovereign_agent/tools/globe_export_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied globe_export_tool.py"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# globe-export-import-d" in text:
    print("SKIP: already patched")
else:
    anchor = [l for l in text.splitlines() if "from .quantum_consult_tool import QuantumConsultTool" in l][0]
    text = text.replace(anchor, anchor + "\nfrom .globe_export_tool import QuantumGlobeExportTool  # globe-export-import-d", 1)
    if '"QuantumConsultTool",  # quantum-mode-all-d' in text:
        text = text.replace('"QuantumConsultTool",  # quantum-mode-all-d',
                            '"QuantumConsultTool",  # quantum-mode-all-d\n    "QuantumGlobeExportTool",  # globe-export-all-d', 1)
    p.write_text(text); print("Patched tools/__init__.py")
PYEOF

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/tools/globe_export_tool.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_globe_export.py" "$REPO_ROOT/tests/test_globe_export.py"
echo "Copied test_globe_export.py → tests/"

echo ""
echo "Running globe export tests..."
"$VENV_PY" -m pytest tests/test_globe_export.py -q

echo ""
echo "=== M95 Globe Export applied successfully ==="
echo "Run quantum_globe_export → data_dir/quantum/globe_export.json for a 3D front-end."
