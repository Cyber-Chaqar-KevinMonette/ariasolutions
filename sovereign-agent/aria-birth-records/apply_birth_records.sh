#!/usr/bin/env bash
# apply_birth_records.sh — Apply M75: founding atoms + lineage tool
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-birth-records"

echo "=== M75: Birth Records & Lineage Tool ==="

# 1. Copy lineage_tool.py into src
echo "→ Copying lineage_tool.py..."
cp "$STAGING/payload/src/sovereign_agent/tools/lineage_tool.py" \
   "$REPO/src/sovereign_agent/tools/lineage_tool.py"

# 2. Patch tools/__init__.py (import + __all__)
INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if ! grep -q "lineage-import-d" "$INIT"; then
    echo "→ Patching tools/__init__.py..."
    # Insert import before the final __all__ line
    python3 - <<'PYEOF'
from pathlib import Path
init = Path("src/sovereign_agent/tools/__init__.py")
content = init.read_text()

IMPORT = '\nfrom .lineage_tool import LineageTool  # lineage-import-d\n'
ALL_ENTRY = '    "LineageTool",  # lineage-all-d\n'

# Insert import before __all__
content = content.replace(
    '\n__all__ = [',
    IMPORT + '\n__all__ = ['
)

# Insert into __all__ before first closing bracket
content = content.replace(
    '    "internet_available",\n    "reset_internet_cache",\n]',
    '    "internet_available",\n    "reset_internet_cache",\n    "LineageTool",  # lineage-all-d\n]'
)

init.write_text(content)
print("  tools/__init__.py patched")
PYEOF
else
    echo "→ tools/__init__.py already patched, skipping"
fi

# 3. Write founding atoms (idempotent)
echo "→ Writing founding atoms..."
cd "$REPO"
.venv/bin/python aria-birth-records/payload/scripts/founding_atoms.py

# 4. Copy and run tests
echo "→ Copying tests..."
cp "$STAGING/tests/test_birth_records.py" "$REPO/tests/test_birth_records.py"

echo "→ Running tests..."
.venv/bin/python -m pytest tests/test_birth_records.py -v --tb=short

echo ""
echo "=== M75 complete ==="
echo "New tool: lineage(birth_only, milestones, tag)"
echo "Founding atoms: 6 written to atoms.ndjson"
