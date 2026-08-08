#!/usr/bin/env bash
# apply_checkpoint_chunks.sh — install Workstream P: god-tier conversation
# checkpoint chunks, an anti-compression system.
#
# Ships:
#   - src/sovereign_agent/checkpoint_chunks/ (new subpackage) — ChunkStore
#     (atomic-write NDJSON, mirrors ApplyQueueStore/EpistemicLedger),
#     ChunkIndex (topic/keyword lookup, generalizes palace.py's Closets),
#     ChunkRecorder (buffers turns, auto-seals every 20).
#   - src/sovereign_agent/tools/recall_chunk_tool.py (new) — RecallChunkTool,
#     Tier 0: returns verbatim chunk text, never a summary.
#   - src/sovereign_agent/tools/__init__.py — anchored import + __all__.
#   - src/sovereign_agent/loop.py — anchored retune of the COMPRESSION
#     ORACLE system-prompt hint: try recall_chunk() before compress_context().
#   - src/sovereign_agent/cockpit/app.py — anchored wiring: every chat line
#     that already flows through _record() also feeds a ChunkRecorder.
#
# Anatomy: guard (cockpit stopped + venv) → backup 3 touched files → copy
# new subpackage/tool → patch (anchored, idempotent) → compile → smoke
# import → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-checkpoint-chunks"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
LOOP="$REPO_ROOT/src/sovereign_agent/loop.py"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
CHUNKS_TARGET="$REPO_ROOT/src/sovereign_agent/checkpoint_chunks"
RECALL_TOOL="$REPO_ROOT/src/sovereign_agent/tools/recall_chunk_tool.py"

echo "=== aria-checkpoint-chunks apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$TOOLS_INIT" "$LOOP" "$APP"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$LOOP" "$BACKUP_DIR/loop.py.bak"
cp "$APP" "$BACKUP_DIR/app.py.bak"

echo "→ Copying checkpoint_chunks/ (new subpackage) + recall_chunk_tool.py (new file)..."
mkdir -p "$CHUNKS_TARGET"
cp "$STAGING"/payload/src/sovereign_agent/checkpoint_chunks/*.py "$CHUNKS_TARGET/"
cp "$STAGING/payload/src/sovereign_agent/tools/recall_chunk_tool.py" "$RECALL_TOOL"

echo "→ Patching tools/__init__.py, loop.py, app.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$TOOLS_INIT" "$LOOP" "$APP" <<'PYEOF'
import sys
from pathlib import Path

staging, tools_init_path, loop_path, app_path = (Path(p) for p in sys.argv[1:5])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app, patch_loop, patch_tools_init

jobs = [
    (tools_init_path, patch_tools_init),
    (loop_path, patch_loop),
    (app_path, patch_app),
]
for path, patch_fn in jobs:
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = patch_fn(text)
    except PatchError as e:
        print(f"ERROR: {path.name}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {path.name}")
    else:
        print(f"  SKIP: {path.name} already patched")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TOOLS_INIT" "$LOOP" "$APP" "$RECALL_TOOL" "$CHUNKS_TARGET"/*.py
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.checkpoint_chunks import ChunkStore, ChunkIndex, ChunkRecorder, Turn
from sovereign_agent.tools.recall_chunk_tool import RecallChunkTool
from sovereign_agent.cockpit import CockpitApp
print('  ✓ imports cleanly (checkpoint_chunks, recall_chunk_tool, cockpit)')
"

cp "$STAGING/tests/test_checkpoint_chunks.py" "$REPO_ROOT/tests/"
echo "Running test suites: checkpoint_chunks (new), loop_utils + cockpit (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_checkpoint_chunks.py" \
  "$REPO_ROOT/tests/test_loop_utils.py" \
  "$REPO_ROOT/tests/test_cockpit.py" \
  -q

echo "=== aria-checkpoint-chunks applied. Reversible: restore the 3 files from $BACKUP_DIR and rm checkpoint_chunks/ + tools/recall_chunk_tool.py 💛 ==="
