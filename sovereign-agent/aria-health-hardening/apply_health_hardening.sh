#!/usr/bin/env bash
# apply_health_hardening.sh — Apply M82: health.py hardening tests
# Idempotent: copies tests and runs them.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-health-hardening"

echo "=== M82: Health Scanner Hardening Tests ==="

# Copy test file
echo "→ Copying test_health_hardening.py..."
cp "$STAGING/tests/test_health_hardening.py" \
   "$REPO/tests/test_health_hardening.py"

# Run tests
echo "→ Running health hardening tests..."
cd "$REPO"
.venv/bin/python -m pytest tests/test_health_hardening.py -v --tb=short

echo ""
echo "=== M82 complete ==="
echo "34 tests added for health.py covering:"
echo "  · HealthReport.ok (no findings, warn-only, error, critical)"
echo "  · HealthReport.summary_line (empty, single, multi-severity)"
echo "  · HealthReport.by_severity (filtering)"
echo "  · _parse_iso_to_seconds (valid ISO, empty, microseconds, invalid)"
echo "  · scan_idle_cycles (EC-DREAM-006 detection, threshold, store exception)"
echo "  · scan_zombies (EC-HEALTH-001 detection, fresh/stale, store exception)"
echo "  · plan_repairs (zombie→reset, idle→pause, lock→remove, unknown, empty)"
echo "  · apply_repairs (dry_run safety — no files touched)"
