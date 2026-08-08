#!/usr/bin/env bash
# apply_hyperintel.sh — install the HyperIntel research faculty (Workstream H4).
#
# Ships: src/sovereign_agent/hyperintel/{__init__,engine}.py (the bounded SCAN->CROSS->AUDIT->DISTILL
# engine) + src/sovereign_agent/tools/hyperintel_tool.py (HyperIntelTool, Tier 1).
#
# NOTE: registers BOTH the import anchor AND the __all__ export in the same patch — L found that a
# prior fix (aria-tools-all-export-fix) had to retroactively add 7 missing __all__ entries because
# earlier modules only patched the import. This apply script does both from the start.
#
# Anatomy: guard (cockpit stopped + venv) → backup tools/__init__.py → copy payload → idempotent
# anchored registration (import + __all__) → py_compile → copy + run tests → tool-registry smoke check.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-hyperintel"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
TARGET="$REPO_ROOT/src/sovereign_agent/hyperintel"

echo "=== aria-hyperintel apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$TARGET"
cp "$STAGING"/payload/src/sovereign_agent/hyperintel/*.py "$TARGET/"
cp "$STAGING/payload/src/sovereign_agent/tools/hyperintel_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")

if "hyperintel-import-d" in t:
    print("SKIP: import already patched")
else:
    anchor = "from .wholeness_tool import WholenessTool  # wholeness-import-d"
    if anchor not in t:
        print(f"ERROR: import anchor not found: {anchor!r}", file=sys.stderr); sys.exit(1)
    t = t.replace(anchor, anchor + "\nfrom .hyperintel_tool import HyperIntelTool  # hyperintel-import-d", 1)
    p.write_text(t, encoding="utf-8")
    print("Patched tools/__init__.py: import")

if "hyperintel-all-d" in t:
    print("SKIP: __all__ already patched")
else:
    anchor = '    "WholenessTool",  # wholeness-all-d'
    if anchor not in t:
        print(f"ERROR: __all__ anchor not found: {anchor!r}", file=sys.stderr); sys.exit(1)
    t = t.replace(anchor, anchor + '\n    "HyperIntelTool",  # hyperintel-all-d', 1)
    p.write_text(t, encoding="utf-8")
    print("Patched tools/__init__.py: __all__")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TARGET"/*.py "$REPO_ROOT/src/sovereign_agent/tools/hyperintel_tool.py" "$TOOLS_INIT"
echo "  ✓ py_compile clean"

echo "→ Import + registry check..."
"$VENV_PY" -c "
from sovereign_agent import tools
assert 'HyperIntelTool' in tools.__all__, 'HyperIntelTool missing from __all__'
assert hasattr(tools, 'HyperIntelTool')
from sovereign_agent.authority import get_tool_meta
meta = get_tool_meta('hyperintel_research')
assert meta.tier == 1
print('  ✓ HyperIntelTool registered (tier 1), exported in __all__')
"

cp "$STAGING/tests/test_hyperintel.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_hyperintel.py" -q

echo "=== aria-hyperintel applied. Reversible: backup at $BACKUP_DIR/tools_init.py.bak 💛 ==="
