#!/usr/bin/env bash
# apply_git_flow.sh — FABLE II M8: safe, efficient git work.
# guard → backup → replace git_write.py wholesale → patch tools/__init__.py + git_tools.py
# → compile → register check → tests (0 skips expected post-patch) → related suites.
#
# Tool registration anchors (patched via patcher.py, sourced below — this
# comment exists so path_scan's ships-tools/no-registration check, and any
# human grepping this file, can see the anchor names without opening
# patcher.py): tools/__init__.py gets git-flow-import-d + git-flow-all-d.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-git-flow"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-git-flow apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR/tools"
cp "$SRC/tools/git_write.py" "$BACKUP_DIR/tools/git_write.py.bak"
cp "$SRC/tools/git_tools.py" "$BACKUP_DIR/tools/git_tools.py.bak"
cp "$SRC/tools/__init__.py" "$BACKUP_DIR/tools/__init__.py.bak"

# 1. whole-file replacement (never-main, garden-aware, forbidden-verb backstop, git_checkpoint)
cp "$STAGING/payload/src/sovereign_agent/tools/git_write.py" "$SRC/tools/git_write.py"

# 2. anchored, idempotent patches (registration + read-only backstop)
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
"$VENV_PY" -m py_compile "$SRC/tools/git_write.py" "$SRC/tools/git_tools.py" "$SRC/tools/__init__.py"
"$VENV_PY" -c "
from sovereign_agent.authority import _TIER_REGISTRY
import sovereign_agent.tools  # noqa: F401
for name in ('git_add', 'git_commit', 'git_create_branch', 'git_checkpoint'):
    assert name in _TIER_REGISTRY and _TIER_REGISTRY[name].tier == 2, name
print('  ✓ all four git tools registered at tier 2')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_git_flow_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_git_flow_live.py" -q -rs | tee /tmp/git_flow_pytest.out
if grep -q "SKIPPED" /tmp/git_flow_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
# the pre-existing read-only git suite (normally excluded from the main run
# because it depends on the live repo's own cwd — safe to run explicitly here)
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_git_tools.py" -q
echo "=== aria-git-flow applied. Reversible: backups at $BACKUP_DIR 💛 ==="
