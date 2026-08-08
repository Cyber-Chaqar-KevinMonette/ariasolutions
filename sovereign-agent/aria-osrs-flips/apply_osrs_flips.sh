#!/usr/bin/env bash
# apply_osrs_flips.sh — Old School RuneScape GE flip trackers.
#
# osrs-flips-d (Kevin, 2026-08-03). Adds: osrs_market.py (pure flip math —
# GE tax + buy limits + staleness + liquidity), OsrsFlipFetcher (I/O),
# 4 capital-tier verticals, the OLD SCHOOL RUNESCAPE Discord category,
# and the fetcher registration.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-osrs-flips"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$STAGING/payload/src/sovereign_agent/osrs_flips"

echo "=== aria-osrs-flips apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then
  echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

mkdir -p "$BACKUP_DIR"
for f in verticals.py discord_admin/blueprint.py discord_runtime/fetchers.py; do
  cp "$REPO_ROOT/src/sovereign_agent/$f" "$BACKUP_DIR/$(basename "$f").bak"
done
echo "→ backed up 3 files to $BACKUP_DIR"

mkdir -p "$REPO_ROOT/src/sovereign_agent/osrs_flips"
cp "$PKG"/*.py "$REPO_ROOT/src/sovereign_agent/osrs_flips/"
echo "→ installed osrs_flips package"

"$VENV_PY" "$PKG/patches.py" "$REPO_ROOT/src/sovereign_agent"

"$VENV_PY" -m py_compile \
  "$REPO_ROOT"/src/sovereign_agent/osrs_flips/*.py \
  "$REPO_ROOT/src/sovereign_agent/verticals.py" \
  "$REPO_ROOT/src/sovereign_agent/discord_admin/blueprint.py" \
  "$REPO_ROOT/src/sovereign_agent/discord_runtime/fetchers.py"
echo "→ compile OK"

cp "$STAGING/tests/test_osrs_flips.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_osrs_flips.py" \
                     "$REPO_ROOT/tests/test_discord_runtime.py" \
                     "$REPO_ROOT/tests/test_bot_health.py" -q \
  || { echo "APPLY-FAIL: tests failed — restore from $BACKUP_DIR"; exit 1; }

echo "=== applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "next: sov scout sync  →  /setup-guild-plan in Discord  →  /setup-webhooks"
