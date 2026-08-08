#!/usr/bin/env bash
# apply_hypothesis_close.sh — M58: hypothesis-close tools
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-hypothesis-close/payload"

echo "=== M58 Hypothesis Close: queue + synthesis + archive tools ==="

# ── 1. Copy tool file ─────────────────────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/tools/hypothesis_close.py" \
   "$REPO/src/sovereign_agent/tools/hypothesis_close.py"
echo "  ✓ hypothesis_close.py"

# ── 2. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if grep -q "M58-hypothesis-close-d" "$TOOLS_INIT"; then
  echo "  ✓ hypothesis-close tools already registered (skipping)"
else
  python3 "$REPO/aria-hypothesis-close/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched"
fi

# ── 3. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-hypothesis-close/tests/test_hypothesis_close.py" \
   "$REPO/tests/test_hypothesis_close.py"
echo "  ✓ tests/test_hypothesis_close.py"

# ── 4. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running hypothesis-close tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_hypothesis_close.py -v --tb=short

echo ""
echo "=== M58 hypothesis-close applied ==="
echo "  HypothesisQueueTool (T0) — list open hypotheses oldest first"
echo "  HypothesisSynthesisTool (T0) — confirm rate + lesson aggregation"
echo "  HypothesisArchiveTool (T1) — mark stale hypotheses as superseded"
