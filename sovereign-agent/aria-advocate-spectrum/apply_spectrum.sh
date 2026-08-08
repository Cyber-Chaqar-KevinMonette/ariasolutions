#!/usr/bin/env bash
# apply_spectrum.sh — the god-tier advocate/audit spectrum (a council of ten lenses).
#   1. src/sovereign_agent/spectrum/  (lenses, council, __init__)
#   2. src/sovereign_agent/tools/spectrum_tools.py — advocate_spectrum(T1)
#   3. tools/__init__.py registration   4. tests   5. run tests
# Reversibility: backups at aria-advocate-spectrum/backups/. Apply via scripts/safe_apply.sh for full guards.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-advocate-spectrum"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-advocate-spectrum apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/spectrum"
cp "$STAGING"/payload/src/sovereign_agent/spectrum/*.py "$REPO_ROOT/src/sovereign_agent/spectrum/"
cp "$STAGING/payload/src/sovereign_agent/tools/spectrum_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied spectrum/ + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# spectrum-import-d" in t:
    print("SKIP: already patched")
else:
    imp = next((l for l in t.splitlines() if "nc-supreme-import-d" in l),
               next((l for l in t.splitlines() if "tribunal-import-d" in l),
                    next((l for l in t.splitlines() if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    t = t.replace(imp, imp + "\nfrom .spectrum_tools import AdvocateSpectrumTool  # spectrum-import-d", 1)
    allk = next((l for l in t.splitlines() if "nc-supreme-all-d" in l),
                next((l for l in t.splitlines() if "tribunal-all-d" in l),
                     next((l for l in t.splitlines() if "constitution-all-d" in l), None)))
    t = t.replace(allk, allk + '\n    "AdvocateSpectrumTool",  # spectrum-all-d', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/spectrum/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/spectrum_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_advocate_spectrum.py" "$REPO_ROOT/tests/test_advocate_spectrum.py"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_advocate_spectrum.py" -q
echo "=== aria-advocate-spectrum applied — the council of ten stands. 💛 ==="
