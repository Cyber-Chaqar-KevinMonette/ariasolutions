#!/usr/bin/env bash
# apply_brain_memory.sh — Stage M97: brain retention (teach + recall, persists across sessions)
#
#   1. src/sovereign_agent/quantum/brain_memory.py
#   2. src/sovereign_agent/tools/brain_memory_tools.py — brain_teach (T1), brain_recall (T0)
#   3. tools/__init__.py: imports + __all__
#   4. test → tests/
# Requires M96 (nested brain). Reversibility: backups at aria-brain-memory/backups/.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-brain-memory"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M97 Brain Memory Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running. Stop it."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi

mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$STAGING/payload/src/sovereign_agent/quantum/brain_memory.py" "$REPO_ROOT/src/sovereign_agent/quantum/"
cp "$STAGING/payload/src/sovereign_agent/tools/brain_memory_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied brain_memory.py + brain_memory_tools.py"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# brain-memory-import-d" in text:
    print("SKIP: already patched")
else:
    anchor = [l for l in text.splitlines() if "council-trust-import-d" in l][0]
    text = text.replace(anchor, anchor + "\nfrom .brain_memory_tools import BrainTeachTool, BrainRecallTool  # brain-memory-import-d", 1)
    if '"CouncilCalibrationTool",' in text:
        text = text.replace('"CouncilCalibrationTool",', '"CouncilCalibrationTool",\n    "BrainTeachTool",  # brain-memory-all-d\n    "BrainRecallTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py (brain memory tools)")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/quantum/brain_memory.py" "$REPO_ROOT/src/sovereign_agent/tools/brain_memory_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_brain_memory.py" "$REPO_ROOT/tests/test_brain_memory.py"
echo "Copied test_brain_memory.py → tests/"

echo ""; echo "Running brain memory tests..."
"$VENV_PY" -m pytest tests/test_brain_memory.py -q
echo ""; echo "=== M97 Brain Memory applied — she retains what she learns across sessions ==="
