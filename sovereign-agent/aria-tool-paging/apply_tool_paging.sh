#!/usr/bin/env bash
# apply_tool_paging.sh — install Keys K5: request_tools dynamic paging
# (bounded, authority-gated) + helpful unknown-tool refusals.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-tool-paging"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOOP_PY="$REPO_ROOT/src/sovereign_agent/loop.py"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
DIET_PY="$REPO_ROOT/src/sovereign_agent/prompt_diet.py"
PAGING="$REPO_ROOT/src/sovereign_agent/tools/tool_paging.py"

echo "=== aria-tool-paging apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$LOOP_PY" "$TOOLS_INIT" "$DIET_PY"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$LOOP_PY" "$BACKUP_DIR/loop.py.bak"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$DIET_PY" "$BACKUP_DIR/prompt_diet.py.bak"

echo "→ Patching loop.py + tools/__init__.py + prompt_diet.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$LOOP_PY" "$TOOLS_INIT" "$DIET_PY" <<'PYEOF'
import sys
from pathlib import Path

staging, loop_p, init_p, diet_p = (Path(a) for a in sys.argv[1:5])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_loop, patch_prompt_diet, patch_tools_init

for name, path, fn in [("loop.py", loop_p, patch_loop),
                       ("tools/__init__.py", init_p, patch_tools_init),
                       ("prompt_diet.py", diet_p, patch_prompt_diet)]:
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
        print(f"  SKIP: {name} already patched")
PYEOF

echo "→ Copying tool_paging.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/tools/tool_paging.py" "$PAGING"

echo "→ Compile + registration check..."
"$VENV_PY" -m py_compile "$LOOP_PY" "$TOOLS_INIT" "$DIET_PY" "$PAGING"
"$VENV_PY" -c "
import sovereign_agent.tools
from sovereign_agent.authority import _TIER_REGISTRY
from sovereign_agent import prompt_diet
assert 'request_tools' in _TIER_REGISTRY and _TIER_REGISTRY['request_tools'].tier == 0
assert 'request_tools' in prompt_diet.CORE_TOOL_NAMES
print('  ✓ request_tools registered (T0) and in the diet core')
"

cp "$STAGING/tests/test_tool_paging_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: tool_paging_live (new), prompt_diet + loop_utils (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_tool_paging_live.py" \
  "$REPO_ROOT/tests/test_prompt_diet_live.py" \
  "$REPO_ROOT/tests/test_loop_utils.py" \
  -q

echo "→ Re-running BOTH smoke gates (live model)..."
bash "$REPO_ROOT/scripts/golden_path_smoke.sh"
bash "$REPO_ROOT/scripts/golden_reflex_smoke.sh"

echo "=== aria-tool-paging applied. Reversible: restore the 3 files from $BACKUP_DIR, rm tool_paging.py 💛 ==="
