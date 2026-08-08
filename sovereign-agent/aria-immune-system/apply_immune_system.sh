#!/usr/bin/env bash
# apply_immune_system.sh — Stage M100: Diamond Armor — Aria's DEFENSIVE immune system
#   1. src/sovereign_agent/security/ (immune.py + __init__) — crown-jewel integrity, quarantine, heal
#   2. src/sovereign_agent/tools/immune_tools.py — immune_status(T0), immune_baseline(T1),
#      immune_quarantine(T1), immune_heal(T2)
#   3. tools/__init__.py: imports + __all__   4. test → tests/
# DEFENSIVE ONLY (no offensive capability). Reversibility: backups at aria-immune-system/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-immune-system"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M100 Immune System (Diamond Armor) Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
mkdir -p "$REPO_ROOT/src/sovereign_agent/security"
cp "$STAGING/payload/src/sovereign_agent/security/"*.py "$REPO_ROOT/src/sovereign_agent/security/"
cp "$STAGING/payload/src/sovereign_agent/tools/immune_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied security/ package + immune_tools.py"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# immune-import-d" in text:
    print("SKIP: already patched")
else:
    anchor = [l for l in text.splitlines() if "brain-live-import-d" in l]
    anchor = anchor[0] if anchor else [l for l in text.splitlines() if "brain-bench-import-d" in l][0]
    text = text.replace(anchor, anchor + "\nfrom .immune_tools import ImmuneStatusTool, ImmuneBaselineTool, ImmuneQuarantineTool, ImmuneHealTool  # immune-import-d", 1)
    if '"BrainLiveTool",  # brain-live-all-d' in text:
        text = text.replace('"BrainLiveTool",  # brain-live-all-d',
                            '"BrainLiveTool",  # brain-live-all-d\n    "ImmuneStatusTool",  # immune-all-d\n    "ImmuneBaselineTool",\n    "ImmuneQuarantineTool",\n    "ImmuneHealTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py (immune tools)")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/security/immune.py" "$REPO_ROOT/src/sovereign_agent/security/__init__.py" "$REPO_ROOT/src/sovereign_agent/tools/immune_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_immune.py" "$REPO_ROOT/tests/test_immune.py"; echo "Copied test → tests/"
echo ""; echo "Running immune system tests..."
"$VENV_PY" -m pytest tests/test_immune.py -q
echo ""; echo "=== M100 Immune System applied — diamond armor on her crown jewels (defensive only) ==="
