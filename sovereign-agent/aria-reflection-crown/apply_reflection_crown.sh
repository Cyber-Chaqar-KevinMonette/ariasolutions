#!/usr/bin/env bash
# apply_reflection_crown.sh — M59: weekly reflection tools
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-reflection-crown/payload"

echo "=== M59 Reflection Crown: WeeklyReflectionTool + ReflectionHistoryTool ==="

# ── 1. Copy tool file ─────────────────────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/tools/reflection_tools.py" \
   "$REPO/src/sovereign_agent/tools/reflection_tools.py"
echo "  ✓ reflection_tools.py"

# ── 2. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if grep -q "M59-reflection-crown-d" "$TOOLS_INIT"; then
  echo "  ✓ reflection tools already registered (skipping)"
else
  python3 "$REPO/aria-reflection-crown/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched"
fi

# ── 3. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-reflection-crown/tests/test_reflection_crown.py" \
   "$REPO/tests/test_reflection_crown.py"
echo "  ✓ tests/test_reflection_crown.py"

# ── 4. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running reflection-crown tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_reflection_crown.py -v --tb=short

echo ""
echo "=== M59 reflection-crown applied ==="
echo "  WeeklyReflectionTool (T0) — weekly synthesis atom"
echo "  ReflectionHistoryTool (T0) — weekly score trend"
echo "  Note: /sentinels cockpit overlay already present from earlier work."
