#!/usr/bin/env bash
# apply_template.sh — the CANONICAL apply-script skeleton for staged aria-* modules.
# This is the reference shape (constitution/tribunal follow it). `new_module.sh` instantiates it,
# substituting shell-corps (kebab-case id) and shell_corps (the payload subpackage, if any).
#
# Anatomy every apply script shares:
#   guard (cockpit stopped + venv present) → backup touched files → copy payload → patch registration
#   (anchored, idempotent) → py_compile → copy tests → run tests.  Reversible: backups under <module>/backups.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-shell-corps"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-shell-corps apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

# 1. copy payload package (edit to match what this module ships)
mkdir -p "$REPO_ROOT/src/sovereign_agent/shell_corps"
cp "$STAGING"/payload/src/sovereign_agent/shell_corps/*.py "$REPO_ROOT/src/sovereign_agent/shell_corps/" 2>/dev/null || true
# cp "$STAGING/payload/src/sovereign_agent/tools/shell-corps_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"

# 2. register tools (anchored + idempotent) — UNCOMMENT + adjust if this module ships tools
# "$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
# import sys; from pathlib import Path
# p=Path(sys.argv[1]); t=p.read_text()
# if "# shell-corps-import-d" in t: print("SKIP: already patched")
# else:
#     anchor=next(l for l in t.splitlines() if "constitution-import-d" in l)
#     t=t.replace(anchor, anchor+"\nfrom .shell-corps_tools import MyTool  # shell-corps-import-d",1)
#     allk=next(l for l in t.splitlines() if "constitution-all-d" in l)
#     t=t.replace(allk, allk+'\n    "MyTool",  # shell-corps-all-d',1)
#     p.write_text(t); print("Patched tools/__init__.py")
# PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/shell_corps/*.py "$TOOLS_INIT" 2>/dev/null || true
# test file is named by PKG (new_module.sh writes test_<PKG>.py), NOT slug —
# they differ for every kebab-case slug, so referencing shell-corps here silently
# skipped the copy + ran pytest on a missing file (hardened 2026-07-19).
[[ -f "$STAGING/tests/test_shell_corps.py" ]] && cp "$STAGING/tests/test_shell_corps.py" "$REPO_ROOT/tests/"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_shell_corps.py -q || \
  { echo "APPLY-FAIL: applied tests did not pass"; exit 1; }
echo "=== aria-shell-corps applied. Reversible: backups at $BACKUP_DIR 💛 ==="
