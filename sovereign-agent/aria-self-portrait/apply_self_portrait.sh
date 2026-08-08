#!/usr/bin/env bash
# apply_self_portrait.sh — Apply M76: self-portrait synthesis tool
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-self-portrait"

echo "=== M76: Self-Portrait Synthesis Tool ==="

# 1. Copy self_portrait_tool.py into src
echo "→ Copying self_portrait_tool.py..."
cp "$STAGING/payload/src/sovereign_agent/tools/self_portrait_tool.py" \
   "$REPO/src/sovereign_agent/tools/self_portrait_tool.py"

# 2. Patch tools/__init__.py (import + __all__)
INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if ! grep -q "self-portrait-import-d" "$INIT"; then
    echo "→ Patching tools/__init__.py..."
    cd "$REPO"
    .venv/bin/python - <<'PYEOF'
from pathlib import Path
init = Path("src/sovereign_agent/tools/__init__.py")
content = init.read_text()

IMPORT = '\nfrom .self_portrait_tool import SelfPortraitTool  # self-portrait-import-d\n'
ALL_ENTRY = '    "SelfPortraitTool",  # self-portrait-all-d\n'

# Insert import before __all__
content = content.replace(
    '\n__all__ = [',
    IMPORT + '\n__all__ = ['
)

# Insert into __all__ before closing bracket
content = content.replace(
    '    "internet_available",\n    "reset_internet_cache",\n]',
    '    "internet_available",\n    "reset_internet_cache",\n    "SelfPortraitTool",  # self-portrait-all-d\n]'
)

init.write_text(content)
print("  tools/__init__.py patched")
PYEOF
else
    echo "→ tools/__init__.py already patched, skipping"
fi

# 3. Copy and run tests
echo "→ Copying tests..."
cp "$STAGING/tests/test_self_portrait.py" "$REPO/tests/test_self_portrait.py"

echo "→ Running tests..."
cd "$REPO"
.venv/bin/python -m pytest tests/test_self_portrait.py -v --tb=short

echo ""
echo "=== M76 complete ==="
echo "New tool: self_portrait(include_narrative, days_for_trend)"
echo "Synthesizes: identity, current_state, growth_trajectory, readiness, capabilities, narrative"
