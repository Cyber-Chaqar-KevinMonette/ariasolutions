#!/usr/bin/env bash
# apply_memory_proof.sh — FABLE II M4: the proving ground grows a memory wing (suite v2).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-memory-proof"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-memory-proof apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/proving_ground/runner.py" "$BACKUP_DIR/runner.py.bak"

# 1. the wing
cp "$STAGING/payload/src/sovereign_agent/proving_ground/memory_wing.py" "$SRC/proving_ground/"

# 2. anchored, idempotent patch (task registry + suite version v2)
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import patch_runner
path = src / "proving_ground" / "runner.py"
text = path.read_text(encoding="utf-8")
new, changed = patch_runner(text)
if changed:
    path.write_text(new, encoding="utf-8"); print("  ✓ proving_ground/runner.py")
else:
    print("  SKIP runner.py (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC"/proving_ground/*.py
"$VENV_PY" -c "
from sovereign_agent.proving_ground.runner import OFFLINE_TASKS, SUITE_VERSION
assert SUITE_VERSION == 'v2', SUITE_VERSION
assert 'compaction-recall' in OFFLINE_TASKS
print(f'  ✓ suite v2 · {len(OFFLINE_TASKS)} tasks')"

# 3. promote the live tests + run them (plus the existing proving suite)
cp "$STAGING/tests/test_memory_proof_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_memory_proof_live.py" "$REPO_ROOT/tests/test_proving_ground_live.py" -q
echo "=== aria-memory-proof applied. Reversible: backups at $BACKUP_DIR 💛 ==="
