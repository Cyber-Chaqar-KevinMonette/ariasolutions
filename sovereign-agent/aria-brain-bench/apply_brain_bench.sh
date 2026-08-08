#!/usr/bin/env bash
# apply_brain_bench.sh — Stage M98: brain speed benchmark + flood-guarded free speech
#   1. src/sovereign_agent/quantum/brain_bench.py
#   2. src/sovereign_agent/tools/brain_bench_tools.py — brain_benchmark (T0), brain_speak (T1)
#   3. tools/__init__.py: imports + __all__   4. test → tests/
# Requires M96+M97. Reversibility: backups at aria-brain-bench/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-brain-bench"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== M98 Brain Bench Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$STAGING/payload/src/sovereign_agent/quantum/brain_bench.py" "$REPO_ROOT/src/sovereign_agent/quantum/"
cp "$STAGING/payload/src/sovereign_agent/tools/brain_bench_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied brain_bench.py + brain_bench_tools.py"

"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# brain-bench-import-d" in text:
    print("SKIP: already patched")
else:
    anchor = [l for l in text.splitlines() if "brain-memory-import-d" in l][0]
    text = text.replace(anchor, anchor + "\nfrom .brain_bench_tools import BrainBenchmarkTool, BrainSpeakTool  # brain-bench-import-d", 1)
    if '"BrainRecallTool",' in text:
        text = text.replace('"BrainRecallTool",', '"BrainRecallTool",\n    "BrainBenchmarkTool",  # brain-bench-all-d\n    "BrainSpeakTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py (brain bench tools)")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/quantum/brain_bench.py" "$REPO_ROOT/src/sovereign_agent/tools/brain_bench_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"
cp "$STAGING/tests/test_brain_bench.py" "$REPO_ROOT/tests/test_brain_bench.py"; echo "Copied test → tests/"
echo ""; echo "Running brain bench tests..."
"$VENV_PY" -m pytest tests/test_brain_bench.py -q
echo ""; echo "=== M98 Brain Bench applied — honest speed + flood-guarded free speech ==="
