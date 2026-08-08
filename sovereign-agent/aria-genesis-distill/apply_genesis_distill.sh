#!/usr/bin/env bash
# apply_genesis_distill.sh — Stage M88: Genesis-Seeds distillation engine + atoms
#
# What this applies:
#   1. src/sovereign_agent/tools/genesis_distill_tool.py — new T1 tool (engine)
#   2. tools/__init__.py: import + __all__ entry for GenesisDistillTool
#   3. Seeds 7 distilled genesis-seed atoms (the buildable lego blocks)
#   4. Copies the test into tests/ (standing suite)
#
# The distilled synthesis lives at:
#   Genesis-Seeds/distilled/quantum_architecture_synthesis.md
#
# Honest frame preserved: quantum-INSPIRED multi-agent architecture, not physics.
# Reversibility: backups at aria-genesis-distill/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-genesis-distill"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M88 Genesis-Seeds Distillation Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo ""

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first, then re-run."
    exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR"

# ── Step 1: Copy the tool ─────────────────────────────────────────────────────
DEST="$REPO_ROOT/src/sovereign_agent/tools/genesis_distill_tool.py"
cp "$STAGING/payload/src/sovereign_agent/tools/genesis_distill_tool.py" "$DEST"
echo "Copied genesis_distill_tool.py → $DEST"

# ── Step 2: Patch tools/__init__.py ──────────────────────────────────────────
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path

p = Path(sys.argv[1])
text = p.read_text()

IMPORT_GUARD  = "# genesis-distill-import-d"
IMPORT_ANCHOR = "from .aria_metrics import AriaMetricsTool  # observability-import-d"
ALL_GUARD     = '"GenesisDistillTool"'
ALL_ANCHOR    = '    "AriaMetricsTool",  # observability-all-d'

if IMPORT_GUARD in text:
    print("SKIP: import patch already applied")
else:
    if IMPORT_ANCHOR not in text:
        print(f"ERROR: import anchor not found: {IMPORT_ANCHOR!r}", file=sys.stderr); sys.exit(1)
    text = text.replace(
        IMPORT_ANCHOR,
        IMPORT_ANCHOR + "\nfrom .genesis_distill_tool import GenesisDistillTool  # genesis-distill-import-d",
        1,
    )
    print("Applied import patch (GenesisDistillTool)")

if ALL_GUARD in text:
    print("SKIP: __all__ already has GenesisDistillTool")
else:
    if ALL_ANCHOR not in text:
        print("WARNING: __all__ anchor not found; skipping __all__ patch")
    else:
        text = text.replace(
            ALL_ANCHOR,
            ALL_ANCHOR + '\n    "GenesisDistillTool",  # genesis-distill-all-d',
            1,
        )
        print("Applied __all__ patch (GenesisDistillTool)")

p.write_text(text)
print("tools/__init__.py written.")
PYEOF

# ── Step 3: Compile check ─────────────────────────────────────────────────────
echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$DEST" "$TOOLS_INIT"
echo "  ✓ files compile cleanly"

# ── Step 4: Seed distilled atoms ──────────────────────────────────────────────
echo ""
echo "→ Seeding genesis-seed atoms..."
"$VENV_PY" "$STAGING/payload/scripts/genesis_atoms.py"

# ── Step 5: Add test to standing suite ────────────────────────────────────────
cp "$STAGING/tests/test_genesis_distill.py" "$REPO_ROOT/tests/test_genesis_distill.py"
echo "Copied test_genesis_distill.py → tests/"

# ── Step 6: Run tests ─────────────────────────────────────────────────────────
echo ""
echo "Running genesis distillation tests..."
"$VENV_PY" -m pytest tests/test_genesis_distill.py -q

echo ""
echo "=== M88 Genesis-Seeds Distillation applied successfully ==="
echo "New tool: genesis_distill (T1). Distilled atoms seeded. Synthesis at"
echo "  Genesis-Seeds/distilled/quantum_architecture_synthesis.md"
echo "Restart sovereign cockpit to load the new tool."
