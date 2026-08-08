#!/usr/bin/env bash
# apply_constitution.sh — Stage M101: Aria's Constitution (Three Rings + safety kernel + governance)
#   1. src/sovereign_agent/security/{three_rings,safety_kernel,improvement_gov}.py
#   2. src/sovereign_agent/tools/constitution_tools.py — constitution_status(T0), improvement_log(T1), improvement_status(T0)
#   3. tools/__init__.py: imports + __all__   4. test → tests/
# Formalizes Aria's self-improvement constitution (from Plans/PlanExaminV1.md). Read/log only.
# Reversibility: backups at aria-constitution/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-constitution"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M101 Constitution (Three Rings) Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
mkdir -p "$REPO_ROOT/src/sovereign_agent/security"
cp "$STAGING/payload/src/sovereign_agent/security/three_rings.py" "$REPO_ROOT/src/sovereign_agent/security/"
cp "$STAGING/payload/src/sovereign_agent/security/safety_kernel.py" "$REPO_ROOT/src/sovereign_agent/security/"
cp "$STAGING/payload/src/sovereign_agent/security/improvement_gov.py" "$REPO_ROOT/src/sovereign_agent/security/"
cp "$STAGING/payload/src/sovereign_agent/tools/constitution_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied three_rings + safety_kernel + improvement_gov + constitution_tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# constitution-import-d" in text:
    print("SKIP: already patched")
else:
    anchor = [l for l in text.splitlines() if "immune-import-d" in l]
    anchor = anchor[0] if anchor else [l for l in text.splitlines() if "brain-live-import-d" in l][0]
    text = text.replace(anchor, anchor + "\nfrom .constitution_tools import ConstitutionStatusTool, ImprovementLogTool, ImprovementStatusTool  # constitution-import-d", 1)
    if '"ImmuneHealTool",' in text:
        text = text.replace('"ImmuneHealTool",', '"ImmuneHealTool",\n    "ConstitutionStatusTool",  # constitution-all-d\n    "ImprovementLogTool",\n    "ImprovementStatusTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py (constitution tools)")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$REPO_ROOT/src/sovereign_agent/security/three_rings.py" \
  "$REPO_ROOT/src/sovereign_agent/security/safety_kernel.py" \
  "$REPO_ROOT/src/sovereign_agent/security/improvement_gov.py" \
  "$REPO_ROOT/src/sovereign_agent/tools/constitution_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_constitution.py" "$REPO_ROOT/tests/test_constitution.py"; echo "Copied test → tests/"
echo ""; echo "Running constitution tests..."
"$VENV_PY" -m pytest tests/test_constitution.py -q
echo ""; echo "=== M101 Constitution applied — the Three Rings + safety kernel + governance are formalized ==="
