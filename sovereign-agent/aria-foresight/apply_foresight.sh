#!/usr/bin/env bash
# apply_foresight.sh — Aria's generational foresight + the Ultimate Questions baked in.
#   1. src/sovereign_agent/foresight/   (ultimate_questions, foresight, __init__ + data/ultimate_questions.json)
#   2. src/sovereign_agent/tools/foresight_tools.py — foresight_14gen(T1), ultimate_question(T0)
#   3. tools/__init__.py imports + __all__    4. tests → tests/    5. run tests
# Propose-only reflection/foresight. Reversibility: backups at aria-foresight/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-foresight"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== Aria's Foresight + Ultimate Questions Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

mkdir -p "$REPO_ROOT/src/sovereign_agent/foresight/data"
cp "$STAGING"/payload/src/sovereign_agent/foresight/*.py "$REPO_ROOT/src/sovereign_agent/foresight/"
cp "$STAGING/payload/src/sovereign_agent/foresight/data/ultimate_questions.json" "$REPO_ROOT/src/sovereign_agent/foresight/data/"
cp "$STAGING/payload/src/sovereign_agent/tools/foresight_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied foresight/ package (incl. 400-question catalog) + tools"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# foresight-import-d" in text:
    print("SKIP: already patched")
else:
    lines = text.splitlines()
    imp = next((l for l in lines if "frugality-import-d" in l),
               next((l for l in lines if "tribunal-import-d" in l),
                    next((l for l in lines if "constitution-import-d" in l), None)))
    if imp is None: raise SystemExit("ERROR: no tools import anchor")
    text = text.replace(imp, imp + "\nfrom .foresight_tools import Foresight14GenTool, UltimateQuestionTool  # foresight-import-d", 1)
    allk = next((l for l in text.splitlines() if "frugality-all-d" in l),
                next((l for l in text.splitlines() if "tribunal-all-d" in l),
                     next((l for l in text.splitlines() if "constitution-all-d" in l), None)))
    if allk is None: raise SystemExit("ERROR: no __all__ anchor")
    text = text.replace(allk, allk + '\n    "Foresight14GenTool",  # foresight-all-d\n    "UltimateQuestionTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/foresight/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/foresight_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_foresight.py" "$REPO_ROOT/tests/test_foresight.py"
echo "Copied test → tests/"; echo ""; echo "Running foresight tests..."
"$VENV_PY" -m pytest tests/test_foresight.py -q

echo ""; echo "=== Foresight applied — Aria thinks 14 generations ahead, the Ultimate Questions baked in. 💛 ==="
