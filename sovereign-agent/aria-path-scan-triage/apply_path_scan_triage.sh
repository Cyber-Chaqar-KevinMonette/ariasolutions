#!/usr/bin/env bash
# apply_path_scan_triage.sh — install Gym #7: status-aware path scanning.
#
# Clears the path sentinel's permanent 32-block error the honest way:
# classify each staged module (applied/pending/unknown via triage.py),
# downgrade findings inside APPLIED modules to historical/* warns in the
# fleet view (scan_repo), while scan_one — the safe_apply step-0 gate —
# keeps FULL block semantics untouched. Also ships the `triage` CLI
# subcommand and SUPERSEDED.md notes for the 3 dangerous stale full-file
# modules (aria-safe-glyphs, aria-inbox-context, aria-inbox-pane).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-path-scan-triage"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SCANNER="$REPO_ROOT/src/sovereign_agent/path_scan/scanner.py"
MAIN="$REPO_ROOT/src/sovereign_agent/path_scan/__main__.py"
TRIAGE="$REPO_ROOT/src/sovereign_agent/path_scan/triage.py"

echo "=== aria-path-scan-triage apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$SCANNER" "$MAIN"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$SCANNER" "$BACKUP_DIR/scanner.py.bak"
cp "$MAIN" "$BACKUP_DIR/__main__.py.bak"

echo "→ Patching scanner.py + __main__.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$SCANNER" "$MAIN" <<'PYEOF'
import sys
from pathlib import Path

staging, scanner_path, main_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_main, patch_scanner

for name, path, fn in [("scanner.py", scanner_path, patch_scanner),
                       ("__main__.py", main_path, patch_main)]:
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
        print(f"  SKIP: {name}")
PYEOF

echo "→ Copying triage.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/path_scan/triage.py" "$TRIAGE"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SCANNER" "$MAIN" "$TRIAGE"
echo "  ✓ py_compile clean"

cp "$STAGING/tests/test_path_scan_triage_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: path_scan_triage_live (new), path_scan (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_path_scan_triage_live.py" \
  "$REPO_ROOT/tests/test_path_scan.py" \
  -q

echo "→ Fleet scan + triage report (live)..."
"$VENV_PY" -m sovereign_agent.path_scan | head -8
"$VENV_PY" -m sovereign_agent.path_scan triage | head -6

echo "=== aria-path-scan-triage applied. Reversible: restore scanner.py/__main__.py from $BACKUP_DIR and rm triage.py 💛 ==="
