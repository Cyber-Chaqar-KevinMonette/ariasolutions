#!/usr/bin/env bash
# apply_brain_live.sh — Stage M99: bounded always-running live mode
#   1. src/sovereign_agent/quantum/brain_live.py
#   2. src/sovereign_agent/tools/brain_live_tool.py — brain_live (T1)
#   3. tools/__init__.py: import + __all__   4. test → tests/
# Requires M96-M98. Bounded, stoppable, output-capped. Reversibility: backups at aria-brain-live/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-brain-live"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M99 Brain Live Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$STAGING/payload/src/sovereign_agent/quantum/brain_live.py" "$REPO_ROOT/src/sovereign_agent/quantum/"
cp "$STAGING/payload/src/sovereign_agent/tools/brain_live_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied brain_live.py + brain_live_tool.py"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# brain-live-import-d" in text:
    print("SKIP: already patched")
else:
    anchor = [l for l in text.splitlines() if "brain-bench-import-d" in l][0]
    text = text.replace(anchor, anchor + "\nfrom .brain_live_tool import BrainLiveTool  # brain-live-import-d", 1)
    if '"BrainSpeakTool",' in text:
        text = text.replace('"BrainSpeakTool",', '"BrainSpeakTool",\n    "BrainLiveTool",  # brain-live-all-d', 1)
    p.write_text(text); print("Patched tools/__init__.py (brain live tool)")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/quantum/brain_live.py" "$REPO_ROOT/src/sovereign_agent/tools/brain_live_tool.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_brain_live.py" "$REPO_ROOT/tests/test_brain_live.py"; echo "Copied test → tests/"
echo ""; echo "Running brain live tests..."
"$VENV_PY" -m pytest tests/test_brain_live.py -q
echo ""; echo "=== M99 Brain Live applied — bounded always-running mode (never floods) ==="
