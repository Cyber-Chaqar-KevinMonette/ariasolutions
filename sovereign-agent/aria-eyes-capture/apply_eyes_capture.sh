#!/usr/bin/env bash
# apply_eyes_capture.sh — install Workstream F's eyes item: wire Aria's
# actual camera frame-grab call, the one deliberately-deferred last mile
# in senses/eyes.py::look_world().
#
# Ships (3 anchored, idempotent patches, no new file):
#   - src/sovereign_agent/senses/eyes.py — a new capture_frame() function.
#     look_world()/see() are completely untouched (proven by a dedicated
#     regression test) — capture stays explicit and opt-in, never
#     automatic, exactly as senses_tools.py's own docstring already states.
#   - src/sovereign_agent/tools/senses_tools.py — a new Tier-1
#     CaptureFrameTool wrapping capture_frame().
#   - src/sovereign_agent/tools/__init__.py — import + __all__ entry for
#     CaptureFrameTool, added together (L's own lesson this session: a
#     missing __all__ entry is a real, recurring bug class).
#
# Anatomy: guard (cockpit stopped + venv) → backup all 3 files → patch
# (anchored, idempotent, py_compile-verified) → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-eyes-capture"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
EYES="$REPO_ROOT/src/sovereign_agent/senses/eyes.py"
SENSES_TOOLS="$REPO_ROOT/src/sovereign_agent/tools/senses_tools.py"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-eyes-capture apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$EYES" "$SENSES_TOOLS" "$TOOLS_INIT"; do [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }; done
mkdir -p "$BACKUP_DIR"
cp "$EYES" "$BACKUP_DIR/eyes.py.bak"
cp "$SENSES_TOOLS" "$BACKUP_DIR/senses_tools.py.bak"
cp "$TOOLS_INIT" "$BACKUP_DIR/__init__.py.bak"

echo "→ Patching all 3 files (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$EYES" "$SENSES_TOOLS" "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path

staging, eyes_path, senses_tools_path, tools_init_path = (Path(p) for p in sys.argv[1:5])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_eyes, patch_senses_tools, patch_tools_init

for label, path, fn in (
    ("eyes.py", eyes_path, patch_eyes),
    ("senses_tools.py", senses_tools_path, patch_senses_tools),
    ("tools/__init__.py", tools_init_path, patch_tools_init),
):
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = fn(text)
    except PatchError as e:
        print(f"ERROR: {label}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {label}")
    else:
        print(f"  SKIP: {label} already patched")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$EYES" "$SENSES_TOOLS" "$TOOLS_INIT"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.senses import eyes
from sovereign_agent.tools.senses_tools import CaptureFrameTool
from sovereign_agent.tools import CaptureFrameTool as _exported
print('  ✓ imports cleanly (eyes.capture_frame, CaptureFrameTool, exported in __all__)')
sight = eyes.look_world()
print(f'  ✓ look_world() unaffected: {sight.detail}')
"

# NOTE: promote test_eyes_capture_live.py, NOT test_eyes_capture.py. The
# latter uses a shadow-copy-and-patch mechanism needed only for pre-apply
# verification; promoting it caused real regressions elsewhere this
# session — see aria-security-strip-wire's README for the full story.
cp "$STAGING/tests/test_eyes_capture_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: eyes_capture_live (new), senses (pre-existing, if present)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_eyes_capture_live.py" \
  -q

echo "=== aria-eyes-capture applied. Reversible: restore all 3 files from $BACKUP_DIR 💛 ==="
