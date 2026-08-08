#!/usr/bin/env bash
# apply_sentinel_fidelity.sh — M63: Defense + Conformance sentinel test suites
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M63 Sentinel Fidelity: Defense + Conformance coverage ==="

# ── 1. Copy test files ────────────────────────────────────────────────────────
cp "$REPO/aria-sentinel-fidelity/tests/test_defense_sentinel.py" \
   "$REPO/tests/test_defense_sentinel.py"
echo "  ✓ tests/test_defense_sentinel.py"

cp "$REPO/aria-sentinel-fidelity/tests/test_conformance_sentinel.py" \
   "$REPO/tests/test_conformance_sentinel.py"
echo "  ✓ tests/test_conformance_sentinel.py"

# ── 2. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running defense sentinel tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_defense_sentinel.py -v --tb=short

echo ""
echo "=== Running conformance sentinel tests ==="
.venv/bin/python -m pytest tests/test_conformance_sentinel.py -v --tb=short

echo ""
echo "=== M63 sentinel-fidelity applied ==="
echo "  DefenseSentinel (414 lines): pressure classification + posture dispatch tested."
echo "  ConformanceSentinel (446 lines): naming rules + standards enforcement tested."
echo "  Both sentinels now have first-class test coverage."
