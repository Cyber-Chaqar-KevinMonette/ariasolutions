#!/usr/bin/env bash
# apply_atoms_compact.sh — M54 atoms compaction sentinel + tools
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-atoms-compact/payload"

echo "=== M54 Atoms Compact: applying sentinel + tools ==="

# ── 1. Copy payload files ─────────────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/stewardship/atoms_compact_sentinel.py" \
   "$REPO/src/sovereign_agent/stewardship/atoms_compact_sentinel.py"
echo "  ✓ atoms_compact_sentinel.py"

cp "$PAYLOAD/src/sovereign_agent/tools/atoms_compact_tool.py" \
   "$REPO/src/sovereign_agent/tools/atoms_compact_tool.py"
echo "  ✓ atoms_compact_tool.py"

# ── 2. Copy tests ─────────────────────────────────────────────────────────
cp "$REPO/aria-atoms-compact/tests/test_atoms_compact_sentinel.py" \
   "$REPO/tests/test_atoms_compact_sentinel.py"
echo "  ✓ tests/test_atoms_compact_sentinel.py"

# ── 3. Register sentinel in stewardship/__init__.py ───────────────────────
INIT="$REPO/src/sovereign_agent/stewardship/__init__.py"

if grep -q "atoms-compact-sentinel-d" "$INIT"; then
  echo "  ✓ sentinel already registered (skipping)"
else
  python3 "$REPO/aria-atoms-compact/patch_stewardship_init.py" "$INIT"
  echo "  ✓ stewardship/__init__.py patched"
fi

# ── 4. Register tools in tools/__init__.py ────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if grep -q "atoms-compact-import-d" "$TOOLS_INIT"; then
  echo "  ✓ tools already imported (skipping)"
else
  python3 "$REPO/aria-atoms-compact/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched"
fi

# ── 5. Run tests ──────────────────────────────────────────────────────────
echo ""
echo "=== Running atoms-compact tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_atoms_compact_sentinel.py -q --tb=short

echo ""
echo "=== M54 atoms-compact applied successfully ==="
echo "  Sentinel 'atoms-compact' now registered."
echo "  Tools: atoms_compact_preview / atoms_compact / atoms_compact_status"
