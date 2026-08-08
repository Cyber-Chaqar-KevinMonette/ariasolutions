#!/usr/bin/env bash
# apply_crossplatform_canon.sh — install Keys K7: the cross-platform canon.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-crossplatform-canon"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-crossplatform-canon apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/tools/__init__.py" "$BACKUP_DIR/tools_init.py.bak"
cp "$SRC/aria_lm/data.py" "$BACKUP_DIR/data.py.bak"

echo "→ Patching tools/__init__.py + aria_lm/data.py..."
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path

staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_data_py, patch_tools_init

for name, path, fn in [("tools/__init__.py", src / "tools" / "__init__.py", patch_tools_init),
                       ("aria_lm/data.py", src / "aria_lm" / "data.py", patch_data_py)]:
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

echo "→ Copying the canon + tool (new files)..."
mkdir -p "$SRC/knowledge/crossplatform"
cp "$STAGING"/payload/src/sovereign_agent/knowledge/crossplatform/*.md "$SRC/knowledge/crossplatform/"
cp "$STAGING/payload/src/sovereign_agent/tools/platform_guide.py" "$SRC/tools/platform_guide.py"

echo "→ Compile + registration check..."
"$VENV_PY" -m py_compile "$SRC/tools/__init__.py" "$SRC/aria_lm/data.py" "$SRC/tools/platform_guide.py"
"$VENV_PY" -c "
import sovereign_agent.tools
from sovereign_agent.authority import _TIER_REGISTRY
assert 'platform_guide' in _TIER_REGISTRY
print('  ✓ platform_guide registered')
"

cp "$STAGING/tests/test_crossplatform_canon_live.py" "$REPO_ROOT/tests/"
echo "Running: crossplatform_canon_live (new) + continual_learning + aria_lm_foundation (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_crossplatform_canon_live.py" \
  "$REPO_ROOT/tests/test_continual_learning_live.py" \
  "$REPO_ROOT/tests/test_aria_lm_foundation.py" \
  -q

echo "=== aria-crossplatform-canon applied. Reversible: restore the 2 files from $BACKUP_DIR, rm knowledge/crossplatform + tools/platform_guide.py 💛 ==="
