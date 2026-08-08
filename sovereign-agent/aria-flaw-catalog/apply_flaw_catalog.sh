#!/usr/bin/env bash
# apply_flaw_catalog.sh — Stage M85a: Flaw Catalog (FlawReadTool T0 + FlawUpdateTool T1)
#
# What this applies:
#   1. src/sovereign_agent/tools/flaw_tools.py       — new file
#   2. tools/__init__.py — import + __all__ entries
#   3. Seeds catalog.ndjson with 7 known walls
#
# Reversibility: app.py not touched. tools/__init__.py backed up.
# Prerequisites: cockpit not running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-flaw-catalog"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M85a Flaw Catalog Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo ""

# ── Guards ────────────────────────────────────────────────────────────────────

if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."
    exit 1
fi

# ── Backups ───────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
cp "$INIT" "$BACKUP_DIR/__init__.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR/__init__.py.bak"

# ── Step 1: Copy flaw_tools.py ───────────────────────────────────────────────

cp "$STAGING/payload/src/sovereign_agent/tools/flaw_tools.py" \
   "$REPO_ROOT/src/sovereign_agent/tools/flaw_tools.py"
echo "Copied flaw_tools.py → src/sovereign_agent/tools/flaw_tools.py"

# ── Step 2: Patch tools/__init__.py ──────────────────────────────────────────

"$VENV_PY" - "$INIT" <<'PYEOF'
import sys
from pathlib import Path

init = Path(sys.argv[1])
text = init.read_text()

IMPORT_GUARD = "# flaw-catalog-import-d"
ALL_GUARD    = "# flaw-catalog-all-d"

if IMPORT_GUARD in text:
    print("SKIP: flaw_tools import already present")
else:
    IMPORT_ANCHOR = "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d"
    if IMPORT_ANCHOR not in text:
        print(f"ERROR: import anchor not found", file=sys.stderr)
        sys.exit(1)
    NEW_IMPORT = (
        "from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d\n"
        "from .flaw_tools import FlawReadTool, FlawUpdateTool  # flaw-catalog-import-d"
    )
    text = text.replace(IMPORT_ANCHOR, NEW_IMPORT, 1)
    print("Added flaw_tools import")

if ALL_GUARD in text:
    print("SKIP: flaw_tools __all__ entries already present")
else:
    ALL_ANCHOR = '"PEIGPortraitTool",  # peig-portrait-all-d'
    if ALL_ANCHOR not in text:
        ALL_ANCHOR = '"LineageTool",  # lineage-all-d'
    if ALL_ANCHOR not in text:
        print("ERROR: __all__ anchor not found", file=sys.stderr)
        sys.exit(1)
    text = text.replace(
        ALL_ANCHOR,
        ALL_ANCHOR + '\n    "FlawReadTool",   # flaw-catalog-all-d\n    "FlawUpdateTool",',
        1,
    )
    print("Added flaw_tools to __all__")

init.write_text(text)
print("tools/__init__.py written.")
PYEOF

# ── Step 3: Seed catalog ──────────────────────────────────────────────────────

echo ""
echo "→ Seeding flaw catalog with known walls..."
"$VENV_PY" "$STAGING/payload/scripts/seed_flaws.py"

# ── Step 4: Compile check ─────────────────────────────────────────────────────

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile \
    "$REPO_ROOT/src/sovereign_agent/tools/flaw_tools.py" \
    "$INIT"
echo "  ✓ compiles"

# ── Step 5: Tests ─────────────────────────────────────────────────────────────

echo ""
echo "→ Running flaw catalog tests..."
"$VENV_PY" -m pytest aria-flaw-catalog/tests/test_flaw_catalog.py -v

echo ""
echo "=== M85a Flaw Catalog applied ==="
echo "New tools: flaw_read (T0) + flaw_update (T1)"
echo "Seeded:    7 known walls in data/flaws/catalog.ndjson"
echo "Restart sovereign cockpit to load new tools."
