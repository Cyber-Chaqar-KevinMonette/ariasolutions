#!/usr/bin/env bash
# apply_vessel_health.sh — install Workstream I: the Vessel-Health organ.
#
# Ships:
#   - src/sovereign_agent/vessel_health.py — NEW file: pure aggregator over
#     kernel-coherence (H2), sentinel health + drift (gather_health()),
#     signal (H3's epistemic ledger), flourishing trend (C's apply-queue/
#     quarantine). CLI: `python -m sovereign_agent.vessel_health`.
#   - src/sovereign_agent/cockpit/app.py — 5 anchored, idempotent patches:
#     module-level cache/lock for the expensive kernel-coherence component
#     (mirrors _SECURITY_SCAN_CACHE exactly), a 4th palette-row strip
#     (#vessel-strip), a 300s background-scan timer (NOT eager on mount —
#     same discipline as aria-security-strip-wire), a new worker + trigger
#     method pair, and a new _refresh_vessel_strip() method. NOT a
#     full-file replace.
#
# Anatomy: guard (cockpit stopped + venv) → backup app.py → patch (anchored,
# idempotent, py_compile-verified) → copy vessel_health.py (new file) →
# copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-vessel-health"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
VESSEL_HEALTH="$REPO_ROOT/src/sovereign_agent/vessel_health.py"

echo "=== aria-vessel-health apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP" ]] || { echo "ERROR: $APP not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP" "$BACKUP_DIR/app.py.bak"

echo "→ Patching app.py (5 anchored edits, idempotent)..."
"$VENV_PY" - "$STAGING" "$APP" <<'PYEOF'
import sys
from pathlib import Path

staging, app_path = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app

text = app_path.read_text(encoding="utf-8")
try:
    new_text, changed = patch_app(text)
except PatchError as e:
    print(f"ERROR: app.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed:
    app_path.write_text(new_text, encoding="utf-8")
    print("  ✓ patched app.py")
else:
    print("  SKIP: app.py already patched")
PYEOF

echo "→ Copying vessel_health.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/vessel_health.py" "$VESSEL_HEALTH"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$APP" "$VESSEL_HEALTH"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp
from sovereign_agent import vessel_health
print('  ✓ imports cleanly (cockpit, vessel_health)')
"

# NOTE: promote test_vessel_health_live.py, NOT test_vessel_health.py. The
# latter uses a shadow-copy-and-patch mechanism needed only for pre-apply
# verification; promoting it caused real regressions elsewhere this
# session — see aria-security-strip-wire's README for the full story.
cp "$STAGING/tests/test_vessel_health_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: vessel_health_live (new), cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_vessel_health_live.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "→ Smoke-testing the CLI (python -m sovereign_agent.vessel_health)..."
"$VENV_PY" -m sovereign_agent.vessel_health

echo "=== aria-vessel-health applied. Reversible: restore app.py from $BACKUP_DIR and rm vessel_health.py 💛 ==="
