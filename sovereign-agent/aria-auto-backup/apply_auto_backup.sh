#!/usr/bin/env bash
# apply_auto_backup.sh — install Gym #3: backups that happen without being asked.
#
# Ships:
#   - src/sovereign_agent/stewardship/backup_sentinel.py — NEW file:
#     BackupSentinel (@register_sentinel, kill switch SOV_NO_BACKUP_SENTINEL).
#     scan() takes + verifies a snapshot when the newest is older than the
#     cadence (default 24h, SOV_BACKUP_CADENCE_HOURS) — the one deliberate
#     exception to propose-only (purely additive/protective; RESTORE stays
#     Tier-3 human-gated, untouched). health_status() is cheap manifest-read
#     only. Backup roots resolve BESIDE the data_dir they protect, so a
#     test-constructed sentinel can never write into the production root.
#   - src/sovereign_agent/backup.py — 2 anchored patches: online SQLite
#     backup for EVERY *.db under data_dir/config_dir (not just atoms/
#     events); the copy walk skips all *.db/-wal/-shm artifacts.
#   - src/sovereign_agent/cockpit/app.py — 3 anchored patches: hourly timer
#     + module-level-guarded @work(thread=True) worker (timer-only, never
#     on mount — the vessel-health discipline, doubly critical here since
#     an eager kickoff in a test boot would write a real snapshot).
#   - src/sovereign_agent/stewardship/__init__.py — registration import.
#
# Anatomy: guard (cockpit stopped + venv) → backup touched files → patch
# (anchored, idempotent, py_compile-verified) → copy payload → tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-auto-backup"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
BACKUP_PY="$REPO_ROOT/src/sovereign_agent/backup.py"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
STEW_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"
SENTINEL="$REPO_ROOT/src/sovereign_agent/stewardship/backup_sentinel.py"

echo "=== aria-auto-backup apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$BACKUP_PY" "$APP_PY" "$STEW_INIT"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$BACKUP_PY" "$BACKUP_DIR/backup.py.bak"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
cp "$STEW_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

echo "→ Patching backup.py, app.py, stewardship/__init__.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$BACKUP_PY" "$APP_PY" "$STEW_INIT" <<'PYEOF'
import sys
from pathlib import Path

staging, backup_path, app_path, init_path = (
    Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
)
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app, patch_backup_py, patch_stewardship_init

def _apply(name, path, fn):
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = fn(text)
    except PatchError as e:
        print(f"ERROR: {name}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {name}")
    else:
        print(f"  SKIP: {name} already patched")

_apply("backup.py", backup_path, patch_backup_py)
_apply("app.py", app_path, patch_app)
_apply("stewardship/__init__.py", init_path, patch_stewardship_init)
PYEOF

echo "→ Copying backup_sentinel.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/stewardship/backup_sentinel.py" "$SENTINEL"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$BACKUP_PY" "$APP_PY" "$STEW_INIT" "$SENTINEL"
echo "  ✓ py_compile clean"

echo "→ Import + registration check..."
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'backup' in registry.registered_ids(), 'backup sentinel not registered'
from sovereign_agent.cockpit import CockpitApp
print('  ✓ backup sentinel registered; cockpit imports cleanly')
"

# NOTE: promote test_auto_backup_live.py, NOT test_auto_backup.py — the
# latter uses a shadow-copy mechanism, staging-only per this session's
# hard-won sys.modules lessons (see aria-security-strip-wire's README).
cp "$STAGING/tests/test_auto_backup_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: auto_backup_live (new), backup (pre-existing), cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_auto_backup_live.py" \
  "$REPO_ROOT/tests/test_backup.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-auto-backup applied. Reversible: restore the 3 files from $BACKUP_DIR and rm backup_sentinel.py 💛 ==="
