#!/usr/bin/env bash
# apply_modes_crown.sh — FABLE II M6: the modes crown (popup + observatory + inner stances).
# guard → backup → copy payload → patch 6 files (tools/cockpit/curiosity/bridge/loop/paging)
# → compile → register check → tests (0 skips expected post-patch) → related suites.
#
# Tool registration anchors (patched via patcher.py, sourced below — this
# comment exists so path_scan's ships-tools/no-registration check, and any
# human grepping this file, can see the anchor names without opening
# patcher.py): tools/__init__.py gets modes-crown-import-d + modes-crown-all-d.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-modes-crown"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-modes-crown apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
for rel in tools/__init__.py cockpit/app.py curiosity.py session_bridge.py \
           loop.py tools/tool_paging.py; do
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp "$SRC/$rel" "$BACKUP_DIR/$rel.bak"
done

# 1. payload packages
mkdir -p "$SRC/modes_crown"
cp "$STAGING"/payload/src/sovereign_agent/modes_crown/*.py "$SRC/modes_crown/"
cp "$STAGING/payload/src/sovereign_agent/tools/stance_tools.py" "$SRC/tools/"
cp "$STAGING/payload/src/sovereign_agent/cockpit/modes_crown_ui.py" "$SRC/cockpit/"

# 2. anchored, idempotent patches
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import ALL_PATCHES
for rel, fn in ALL_PATCHES.items():
    path = src / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC"/modes_crown/*.py "$SRC/tools/stance_tools.py" \
  "$SRC/cockpit/modes_crown_ui.py" "$SRC/tools/__init__.py" "$SRC/cockpit/app.py" \
  "$SRC/curiosity.py" "$SRC/session_bridge.py" "$SRC/loop.py" "$SRC/tools/tool_paging.py"
"$VENV_PY" -c "
from sovereign_agent.authority import _TIER_REGISTRY
import sovereign_agent.tools  # noqa: F401
assert 'set_stance' in _TIER_REGISTRY and 'observatory' in _TIER_REGISTRY
print('  ✓ set_stance + observatory registered')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_modes_crown_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_modes_crown_live.py" -q -rs | tee /tmp/modes_crown_pytest.out
if grep -q "SKIPPED" /tmp/modes_crown_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_curiosity_qa_live.py" \
  "$REPO_ROOT/tests/test_session_bridge_live.py" \
  "$REPO_ROOT/tests/test_tool_paging_live.py" \
  "$REPO_ROOT/tests/test_cache_crown.py" -q
echo "=== aria-modes-crown applied. Reversible: backups at $BACKUP_DIR 💛 ==="
