#!/usr/bin/env bash
# apply_quantum_mode.sh — Stage M89: the Non-Classical Layer (13-node globe council)
#
# What this applies:
#   1. src/sovereign_agent/quantum/  — new pure-Python package (field, globe, memory,
#      coherence_gate, maturity, council). Quantum-INSPIRED, advisory-only, zero new deps.
#   2. src/sovereign_agent/tools/quantum_portrait_tool.py (T0) + quantum_consult_tool.py (T1)
#   3. tools/__init__.py: imports + __all__ entries
#   4. Copies the test into tests/ (standing suite)
#
# Distilled from Kevin's Genesis-Seeds research (Genesis-Seeds/distilled/blocks/LEGO_BLOCKS.md,
# BUILD_READY.md). Advisory only: never gates actions, never raises authority, never self-modifies.
#
# Reversibility: backups at aria-quantum-mode/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-quantum-mode"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M89 Non-Classical Layer (Quantum Mode) Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo ""

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first, then re-run."
    exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."; exit 1
fi

mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR"

# ── Step 1: Copy the quantum package ──────────────────────────────────────────
mkdir -p "$REPO_ROOT/src/sovereign_agent/quantum"
cp "$STAGING/payload/src/sovereign_agent/quantum/"*.py "$REPO_ROOT/src/sovereign_agent/quantum/"
echo "Copied quantum/ package → src/sovereign_agent/quantum/"

# ── Step 2: Copy the tools ────────────────────────────────────────────────────
cp "$STAGING/payload/src/sovereign_agent/tools/quantum_portrait_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"
cp "$STAGING/payload/src/sovereign_agent/tools/quantum_consult_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"
cp "$STAGING/payload/src/sovereign_agent/tools/quantum_evolve_tool.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied quantum tools → src/sovereign_agent/tools/"

# ── Step 3: Patch tools/__init__.py ──────────────────────────────────────────
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()

IMPORT_GUARD  = "# quantum-mode-import-d"
IMPORT_ANCHOR = "from .genesis_distill_tool import GenesisDistillTool  # genesis-distill-import-d"
ALL_GUARD     = '"QuantumPortraitTool"'
ALL_ANCHOR    = '    "GenesisDistillTool",  # genesis-distill-all-d'

if IMPORT_GUARD in text:
    print("SKIP: import patch already applied")
else:
    if IMPORT_ANCHOR not in text:
        print(f"ERROR: import anchor not found", file=sys.stderr); sys.exit(1)
    text = text.replace(
        IMPORT_ANCHOR,
        IMPORT_ANCHOR
        + "\nfrom .quantum_portrait_tool import QuantumPortraitTool  # quantum-mode-import-d"
        + "\nfrom .quantum_consult_tool import QuantumConsultTool  # quantum-mode-import-d"
        + "\nfrom .quantum_evolve_tool import QuantumEvolveTool  # quantum-mode-import-d",
        1)
    print("Applied import patch (QuantumPortraitTool, QuantumConsultTool, QuantumEvolveTool)")

if ALL_GUARD in text:
    print("SKIP: __all__ already patched")
else:
    if ALL_ANCHOR not in text:
        print("WARNING: __all__ anchor not found; skipping")
    else:
        text = text.replace(
            ALL_ANCHOR,
            ALL_ANCHOR
            + '\n    "QuantumPortraitTool",  # quantum-mode-all-d'
            + '\n    "QuantumConsultTool",  # quantum-mode-all-d'
            + '\n    "QuantumEvolveTool",  # quantum-mode-all-d',
            1)
        print("Applied __all__ patch")

p.write_text(text)
print("tools/__init__.py written.")
PYEOF

# ── Step 4: Compile check ─────────────────────────────────────────────────────
echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$REPO_ROOT/src/sovereign_agent/quantum/"*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/quantum_portrait_tool.py" \
  "$REPO_ROOT/src/sovereign_agent/tools/quantum_consult_tool.py" \
  "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

# ── Step 5: Add test to standing suite ────────────────────────────────────────
cp "$STAGING/tests/test_quantum_mode.py" "$REPO_ROOT/tests/test_quantum_mode.py"
echo "Copied test_quantum_mode.py → tests/"

# ── Step 6: Run tests ─────────────────────────────────────────────────────────
echo ""
echo "Running non-classical layer tests..."
"$VENV_PY" -m pytest tests/test_quantum_mode.py -q

echo ""
echo "=== M89 Non-Classical Layer applied successfully ==="
echo "New: sovereign_agent.quantum (13-node globe), tools quantum_portrait (T0) + quantum_consult (T1)."
echo "Advisory only. Restart sovereign cockpit to load. Try: sov ask 'run quantum_portrait'"
