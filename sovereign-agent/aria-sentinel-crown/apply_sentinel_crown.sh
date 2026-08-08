#!/usr/bin/env bash
# apply_sentinel_crown.sh — M55: activate the dormant sentinel squad
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M55 Sentinel Crown: activating dormant sentinels ==="

# ── 1. Add SENTINEL_REGISTRY alias to registry.py ────────────────────────────
REGISTRY="$REPO/src/sovereign_agent/stewardship/registry.py"

if grep -q "sentinel-registry-alias-d" "$REGISTRY"; then
  echo "  ✓ SENTINEL_REGISTRY alias already present (skipping)"
else
  python3 "$REPO/aria-sentinel-crown/patch_registry.py" "$REGISTRY"
  echo "  ✓ registry.py patched (SENTINEL_REGISTRY alias added)"
fi

# ── 2. Register 8 dormant sentinels in stewardship/__init__.py ───────────────
INIT="$REPO/src/sovereign_agent/stewardship/__init__.py"

if grep -q "M55-sentinel-crown-d" "$INIT"; then
  echo "  ✓ sentinels already registered (skipping)"
else
  python3 "$REPO/aria-sentinel-crown/patch_stewardship_init.py" "$INIT"
  echo "  ✓ stewardship/__init__.py patched (8 sentinels registered)"
fi

# ── 3. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-sentinel-crown/tests/test_sentinel_crown.py" \
   "$REPO/tests/test_sentinel_crown.py"
echo "  ✓ tests/test_sentinel_crown.py"

# ── 4. Run tests ─────────────────────────────────────────────────────────────
echo ""
echo "=== Running sentinel-crown tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_sentinel_crown.py -v --tb=short

echo ""
echo "=== M55 sentinel-crown applied ==="
echo "  11+ sentinels now registered. Run: sov sentinels list"
