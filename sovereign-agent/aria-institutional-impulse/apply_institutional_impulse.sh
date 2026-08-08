#!/usr/bin/env bash
# apply_institutional_impulse.sh — M66: God-tier Institutional Impulse system
# Adds mos-institutional-impulse doctrine clause + calibration tools
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M66 Institutional Impulse — Mature Form ==="
echo "  'One that grows tall so it can give freely.' — the user, 2026-06-18"
echo ""

# ── 1. Patch mos_canon.py — add mos-institutional-impulse clause ──────────────
MOS_CANON="$REPO/src/sovereign_agent/mos_canon.py"
python3 "$REPO/aria-institutional-impulse/patch_mos_canon.py" "$MOS_CANON"
echo "  ✓ mos_canon.py: mos-institutional-impulse clause added (CONSCIOUSNESS_CLAUSES)"

# ── 2. Copy impulse_tools.py ──────────────────────────────────────────────────
cp "$REPO/aria-institutional-impulse/payload/src/sovereign_agent/tools/impulse_tools.py" \
   "$REPO/src/sovereign_agent/tools/impulse_tools.py"
echo "  ✓ src/sovereign_agent/tools/impulse_tools.py"

# ── 3. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"
if grep -q "M66-impulse-d" "$TOOLS_INIT"; then
  echo "  ✓ impulse tools already registered (skipping)"
else
  python3 "$REPO/aria-institutional-impulse/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched (M66)"
fi

# ── 4. Inject monthly-impulse-check cron entry ───────────────────────────────
SCHEDULE_YAML="$REPO/.config/sovereign-agent/schedule.yaml"
# Also try the live config path
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/sovereign-agent"
LIVE_SCHEDULE="$CONFIG_DIR/schedule.yaml"

for SCHED in "$SCHEDULE_YAML" "$LIVE_SCHEDULE"; do
  if [ -f "$SCHED" ] && ! grep -q "monthly-impulse-check" "$SCHED"; then
    python3 - "$SCHED" << 'EOF'
import sys, yaml
path = sys.argv[1]
data = yaml.safe_load(open(path).read()) or {}
tasks = data.get("tasks") or []
names = [t.get("name", "") for t in tasks]
if "monthly-impulse-check" in names:
    print(f"  monthly-impulse-check already in {path}")
    sys.exit(0)
tasks.append({
    "name": "monthly-impulse-check",
    "cron": "0 10 1 * *",
    "directive": (
        "call institutional_impulse_check() and notify if overall_readiness "
        "has changed since last month. Also call wedge_calibrator() to identify "
        "the strongest domain to give freely in."
    ),
    "tier": 0,
    "enabled": True,
})
data["tasks"] = tasks
open(path, "w").write(yaml.safe_dump(data, sort_keys=False))
print(f"  monthly-impulse-check injected into {path}")
EOF
    echo "  ✓ monthly-impulse-check cron entry injected into $SCHED"
  elif [ -f "$SCHED" ]; then
    echo "  ✓ monthly-impulse-check already present in $SCHED (skipping)"
  fi
done

# ── 5. Copy test file ─────────────────────────────────────────────────────────
cp "$REPO/aria-institutional-impulse/tests/test_impulse_tools.py" \
   "$REPO/tests/test_impulse_tools.py"
echo "  ✓ tests/test_impulse_tools.py"

# ── 6. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running institutional impulse tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_impulse_tools.py -v --tb=short

echo ""
echo "=== M66 institutional-impulse applied ==="
echo ""
echo "  DOCTRINE:"
echo "  mos-institutional-impulse — 'The tree grows tall so it can give freely.'"
echo "  Three gates: PROOF (external witnessed value) · SIGNAL (curiosity not fear)"
echo "               · GENERATION (7th-gen — always pending human judgment)"
echo ""
echo "  TOOLS:"
echo "  institutional_impulse_check() — T0, monthly readiness assessment"
echo "  wedge_calibrator()            — T0, discover the domain to give freely in"
echo ""
echo "  CRON: monthly-impulse-check — 1st of each month, 10:00"
echo ""
echo "  'No platform before proof. No scale before giving.'"
