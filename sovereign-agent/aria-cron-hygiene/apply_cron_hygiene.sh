#!/usr/bin/env bash
# apply_cron_hygiene.sh — M56: schedule sentinel + default hygiene entries
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-cron-hygiene/payload"

echo "=== M56 Cron Hygiene: schedule sentinel + default entries ==="

# ── 1. Copy sentinel file ─────────────────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/stewardship/schedule_sentinel.py" \
   "$REPO/src/sovereign_agent/stewardship/schedule_sentinel.py"
echo "  ✓ schedule_sentinel.py"

# ── 2. Register in stewardship/__init__.py ────────────────────────────────────
INIT="$REPO/src/sovereign_agent/stewardship/__init__.py"

if grep -q "M56-cron-hygiene-d" "$INIT"; then
  echo "  ✓ schedule sentinel already registered (skipping)"
else
  python3 "$REPO/aria-cron-hygiene/patch_init.py" "$INIT"
  echo "  ✓ stewardship/__init__.py patched"
fi

# ── 3. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-cron-hygiene/tests/test_cron_hygiene.py" \
   "$REPO/tests/test_cron_hygiene.py"
echo "  ✓ tests/test_cron_hygiene.py"

# ── 4. Provision default schedule entries ─────────────────────────────────────
python3 "$REPO/aria-cron-hygiene/provision_schedule.py"
echo "  ✓ default schedule entries provisioned"

# ── 5. Run tests ─────────────────────────────────────────────────────────────
echo ""
echo "=== Running cron-hygiene tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_cron_hygiene.py -v --tb=short

echo ""
echo "=== M56 cron-hygiene applied ==="
echo "  ScheduleSentinel registered. Run: sov sentinels scan schedule"
