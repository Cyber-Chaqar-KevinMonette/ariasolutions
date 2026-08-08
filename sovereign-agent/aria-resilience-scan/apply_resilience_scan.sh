#!/usr/bin/env bash
# apply_resilience_scan.sh — resilience/robustness/edge-case scanners for both layers.
#   1. src/sovereign_agent/resilience_scan/  (probes, scanner, layers, __init__)
#   2. src/sovereign_agent/stewardship/resilience_sentinel.py  (@register_sentinel)
#   3. src/sovereign_agent/tools/resilience_scan_tools.py — resilience_scan(T0)
#   4. tools/__init__.py + stewardship/__init__.py registration   5. tests   6. run tests
# Reversibility: backups at aria-resilience-scan/backups/. Apply via scripts/safe_apply.sh for full guards.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-resilience-scan"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
STEW_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"

echo "=== aria-resilience-scan apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"; cp "$STEW_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/resilience_scan"
cp "$STAGING"/payload/src/sovereign_agent/resilience_scan/*.py "$REPO_ROOT/src/sovereign_agent/resilience_scan/"
cp "$STAGING/payload/src/sovereign_agent/stewardship/resilience_sentinel.py" "$REPO_ROOT/src/sovereign_agent/stewardship/"
cp "$STAGING/payload/src/sovereign_agent/tools/resilience_scan_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied resilience_scan/ + sentinel + tool"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# resilience-scan-import-d" in t:
    print("SKIP tools: already patched")
else:
    imp = next((l for l in t.splitlines() if "spectrum-import-d" in l),
               next((l for l in t.splitlines() if "nc-supreme-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .resilience_scan_tools import ResilienceScanTool  # resilience-scan-import-d", 1)
    allk = next((l for l in t.splitlines() if "spectrum-all-d" in l),
                next((l for l in t.splitlines() if "nc-supreme-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "ResilienceScanTool",  # resilience-scan-all-d', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

"$VENV_PY" - "$STEW_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "resilience-sentinel-d" in t:
    print("SKIP stewardship: already patched")
else:
    anchor = next((l for l in t.splitlines() if "godtier-sentinel-d" in l),
                  next((l for l in t.splitlines() if "tribunal-sentinel-d" in l),
                       next((l for l in t.splitlines() if "sentinel-crown-d" in l), None)))
    if anchor is None: raise SystemExit("ERROR: no stewardship sentinel anchor")
    t = t.replace(anchor, anchor + "\nfrom . import resilience_sentinel as _resilience_sentinel              # noqa: F401  # resilience-sentinel-d", 1)
    p.write_text(t); print("Patched stewardship/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/resilience_scan/*.py \
  "$REPO_ROOT/src/sovereign_agent/stewardship/resilience_sentinel.py" \
  "$REPO_ROOT/src/sovereign_agent/tools/resilience_scan_tools.py" "$TOOLS_INIT" "$STEW_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_resilience_scan.py" "$REPO_ROOT/tests/test_resilience_scan.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_resilience_scan.py" -q
echo "=== aria-resilience-scan applied — both layers probed for resilience. 💛 ==="
