#!/usr/bin/env bash
# apply_continuation_hardening.sh — Apply M81: continuation.py hardening tests
# Idempotent: copies tests and runs them.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-continuation-hardening"

echo "=== M81: Continuation Hardening Tests ==="

# Copy test file
echo "→ Copying test_continuation_hardening.py..."
cp "$STAGING/tests/test_continuation_hardening.py" \
   "$REPO/tests/test_continuation_hardening.py"

# Run tests
echo "→ Running continuation hardening tests..."
cd "$REPO"
.venv/bin/python -m pytest tests/test_continuation_hardening.py -v --tb=short

echo ""
echo "=== M81 complete ==="
echo "38 tests added for continuation.py covering:"
echo "  · format_elapsed (None/seconds/minutes/hours)"
echo "  · Continuation properties (cursor, progress, model affinity, elapsed, is_drained)"
echo "  · update_status_from_steps (done, poisoned, paused preservation)"
echo "  · YAML roundtrip + corrupt-input rejection"
echo "  · ContinuationStore (create, get, lock, delete, concurrent lock exclusion)"
