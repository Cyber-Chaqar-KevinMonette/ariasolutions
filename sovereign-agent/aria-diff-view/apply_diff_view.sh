#!/usr/bin/env bash
# apply_template.sh — the CANONICAL apply-script skeleton for staged aria-* modules.
# This is the reference shape (constitution/tribunal follow it). `new_module.sh` instantiates it,
# substituting diff-view (kebab-case id) and diff_view (the payload subpackage, if any).
#
# Anatomy every apply script shares:
#   guard (cockpit stopped + venv present) → backup touched files → copy payload → patch registration
#   (anchored, idempotent) → py_compile → copy tests → run tests.  Reversible: backups under <module>/backups.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-diff-view"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-diff-view apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

# 1. copy payload package (edit to match what this module ships)
mkdir -p "$REPO_ROOT/src/sovereign_agent/diff_view"
cp "$STAGING"/payload/src/sovereign_agent/diff_view/*.py "$REPO_ROOT/src/sovereign_agent/diff_view/" 2>/dev/null || true
# cp "$STAGING/payload/src/sovereign_agent/tools/diff-view_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"

# 2. register tools (anchored + idempotent) — UNCOMMENT + adjust if this module ships tools
# "$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
# import sys; from pathlib import Path
# p=Path(sys.argv[1]); t=p.read_text()
# if "# diff-view-import-d" in t: print("SKIP: already patched")
# else:
#     anchor=next(l for l in t.splitlines() if "constitution-import-d" in l)
#     t=t.replace(anchor, anchor+"\nfrom .diff-view_tools import MyTool  # diff-view-import-d",1)
#     allk=next(l for l in t.splitlines() if "constitution-all-d" in l)
#     t=t.replace(allk, allk+'\n    "MyTool",  # diff-view-all-d',1)
#     p.write_text(t); print("Patched tools/__init__.py")
# PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/diff_view/*.py "$TOOLS_INIT" 2>/dev/null || true
[[ -f "$STAGING/tests/test_diff_view.py" ]] && cp "$STAGING/tests/test_diff_view.py" "$REPO_ROOT/tests/"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_diff_view.py -q || \
  { echo "APPLY-FAIL: applied tests did not pass"; exit 1; }
echo "=== aria-diff-view applied. Reversible: backups at $BACKUP_DIR 💛 ==="
