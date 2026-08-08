#!/usr/bin/env bash
# apply_prompt_diet.sh — install Gym #9: mode-aware prompt + tool-schema diet.
#
# The golden-reflex gate's first live run caught the real problem: the
# ~32K-char system prompt (~8K tokens) plus 213 tool schemas (~40K tokens)
# were being sent into the oneshot tool-use model's HARD 8,192 context —
# prompt_tokens pinned at exactly 8192, 17 junk completion tokens, empty
# final_message. The model never saw an untruncated request.
#
# Ships prompt_diet.py (section diet + curated core toolset for
# short-horizon modes, kill switch SOV_NO_PROMPT_DIET=1 → byte-identical
# behavior) + 4 anchored loop.py patches. Acceptance: BOTH smoke gates
# (golden path + golden reflex) pass live with the diet on — run at the end.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-prompt-diet"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOOP_PY="$REPO_ROOT/src/sovereign_agent/loop.py"
CLI_PY="$REPO_ROOT/src/sovereign_agent/cli.py"
DIET_PY="$REPO_ROOT/src/sovereign_agent/prompt_diet.py"

echo "=== aria-prompt-diet apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$LOOP_PY" ]] || { echo "ERROR: $LOOP_PY not found."; exit 1; }
[[ -f "$CLI_PY" ]] || { echo "ERROR: $CLI_PY not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$LOOP_PY" "$BACKUP_DIR/loop.py.bak"
cp "$CLI_PY" "$BACKUP_DIR/cli.py.bak"

echo "→ Patching loop.py (4 anchored edits) + cli.py (the 15-tool registry fix)..."
"$VENV_PY" - "$STAGING" "$LOOP_PY" "$CLI_PY" <<'PYEOF'
import sys
from pathlib import Path

staging, loop_path, cli_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_cli, patch_loop

for name, path, fn in [("loop.py", loop_path, patch_loop), ("cli.py", cli_path, patch_cli)]:
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

echo "→ Copying prompt_diet.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/prompt_diet.py" "$DIET_PY"

echo "→ Compile + import check..."
"$VENV_PY" -m py_compile "$LOOP_PY" "$CLI_PY" "$DIET_PY"
"$VENV_PY" -c "
from sovereign_agent.loop import _system_prompt
from sovereign_agent.modes import Mode
for m in Mode:
    p = _system_prompt(m)
    print(f'  {m.value:8} prompt: {len(p)} chars')
"

cp "$STAGING/tests/test_prompt_diet_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: prompt_diet_live (new), loop_utils (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_prompt_diet_live.py" \
  "$REPO_ROOT/tests/test_loop_utils.py" \
  -q

echo "→ ACCEPTANCE: both smoke gates, live, with the diet on..."
bash "$REPO_ROOT/scripts/golden_path_smoke.sh"
bash "$REPO_ROOT/scripts/golden_reflex_smoke.sh"

echo "=== aria-prompt-diet applied. Reversible: restore loop.py from $BACKUP_DIR, rm prompt_diet.py (or just set SOV_NO_PROMPT_DIET=1) 💛 ==="
