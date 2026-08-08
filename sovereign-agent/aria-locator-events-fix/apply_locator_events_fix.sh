#!/usr/bin/env bash
# apply_locator_events_fix.sh — fix LocatorSentinel's stale events_log expectation.
#
# THE BUG (found in the 2026-07-02 full-system scan, root-caused 2026-07-03): LocatorSentinel's
# default events_log entry expects a flat `<data_dir>/events.jsonl` file. But config.py's events
# system has long since moved to daily-rotated files (`events_dir/events-YYYY-MM-DD.jsonl`) — the
# flat file is never created, so `sov sentinels scan` reports a false "missing" warning on every
# real installation, even ones (like this one) that have been actively emitting events since April.
#
# THE FIX: point the default entry at `events_dir` (expected_kind="dir") instead of the flat file.
# Verified: 4/4 tests pass — normal fresh-install behavior preserved (still flags a truly-absent
# events_dir as missing), while a real data_dir with rotated files now scans clean.
#
# ALSO: the EXISTING on-disk catalog (~/.local/share/sovereign-agent/sentinels/locator/catalogs/
# locations.json) already baked in the old, wrong entry when it was first seeded — fixing the
# source alone doesn't fix an installation that already has a catalog file. Locator's own catalog
# is a derived/cache-like index (see its own docstring: "does NOT maintain its catalog by hand"),
# so removing the stale on-disk copy so it re-seeds fresh on next scan is the correct, safe,
# in-scope action for Locator's own Tier-1 surface — backed up first, not deleted blind.
#
# Anatomy: guard (cockpit stopped + venv) → backup touched files (source + the live catalog, if
# present) → patch source (anchored, idempotent) → remove the stale on-disk catalog so it re-seeds
# → py_compile → copy + run tests → re-scan to prove the false-positive is gone.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-locator-events-fix"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOCATOR="$REPO_ROOT/src/sovereign_agent/stewardship/locator_sentinel.py"

echo "=== aria-locator-events-fix apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$LOCATOR" ]] || { echo "ERROR: $LOCATOR not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$LOCATOR" "$BACKUP_DIR/locator_sentinel.py.bak"

# 1. patch the source (anchored, idempotent)
"$VENV_PY" - "$LOCATOR" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")

MARK = "locator-events-fix-d"
if MARK in t:
    print("SKIP: already patched")
else:
    old = (
        '            LocationEntry(\n'
        '                key="events_log",\n'
        '                path=str(self._data_dir / "events.jsonl"),\n'
        '                purpose="cross-system event audit trail",\n'
        '                owner_sentinel="system",\n'
        '                expected_kind="file",\n'
        '                criticality="warning",\n'
        '            ),\n'
    )
    if old not in t:
        print(f"ERROR: events_log LocationEntry block not found verbatim", file=sys.stderr)
        sys.exit(1)
    new = (
        f'            LocationEntry(  # {MARK}\n'
        '                key="events_log",\n'
        '                path=str(self._data_dir / "events"),\n'
        '                purpose="cross-system event audit trail (daily-rotated dir)",\n'
        '                owner_sentinel="system",\n'
        '                expected_kind="dir",\n'
        '                criticality="warning",\n'
        '            ),\n'
    )
    t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print("Patched locator_sentinel.py: events_log now checks events_dir")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$LOCATOR"
echo "  ✓ py_compile clean"

# 2. remove the stale on-disk catalog (Locator's own derived index — safe to re-seed, backed up first)
CATALOG="$HOME/.local/share/sovereign-agent/sentinels/locator/catalogs/locations.json"
if [[ -f "$CATALOG" ]] && grep -q "events.jsonl" "$CATALOG"; then
  cp "$CATALOG" "$BACKUP_DIR/locations.json.bak"
  rm "$CATALOG"
  echo "  ✓ removed stale on-disk catalog (backup at $BACKUP_DIR/locations.json.bak) — will re-seed on next scan"
else
  echo "  · no stale on-disk catalog found (fresh install, or already re-seeded)"
fi

cp "$STAGING/tests/test_locator_events_fix.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_locator_events_fix.py" -q

echo "→ Re-scanning the real installation to confirm the false-positive is gone..."
"$VENV_PY" -c "
from sovereign_agent.config import SETTINGS
from sovereign_agent.stewardship.locator_sentinel import LocatorSentinel
s = LocatorSentinel(SETTINGS.paths.data_dir)
report = s.scan()
events_findings = [f for f in report.details['findings'] if f['key'] == 'events_log']
if events_findings:
    print(f'  ✗ still flagged: {events_findings}')
    raise SystemExit(1)
print('  ✓ events_log no longer flagged on the real installation')
"

echo "=== aria-locator-events-fix applied. Reversible: backups at $BACKUP_DIR 💛 ==="
