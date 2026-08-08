#!/usr/bin/env bash
# apply_watchdog_tests.sh — M62: first test suite for WatchdogSentinel
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M62 Watchdog Tests: golden-image integrity coverage ==="

# ── 1. Copy test file ─────────────────────────────────────────────────────────
cp "$REPO/aria-watchdog-tests/tests/test_watchdog_sentinel.py" \
   "$REPO/tests/test_watchdog_sentinel.py"
echo "  ✓ tests/test_watchdog_sentinel.py"

# ── 2. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running watchdog sentinel tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_watchdog_sentinel.py -v --tb=short

echo ""
echo "=== M62 watchdog-tests applied ==="
echo "  WatchdogSentinel (475 lines) now has dedicated test coverage."
echo "  20 tests covering: seal/drift/missing/health/concurrency/atomicity/recovery"
