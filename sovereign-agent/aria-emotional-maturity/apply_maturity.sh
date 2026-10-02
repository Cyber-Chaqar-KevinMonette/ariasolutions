#!/usr/bin/env bash
# apply_template.sh — the CANONICAL apply-script skeleton for staged aria-* modules.
# This is the reference shape (constitution/tribunal follow it). `new_module.sh` instantiates it,
# substituting emotional-maturity (kebab-case id) and maturity (the payload subpackage, if any).
#
# Anatomy every apply script shares:
#   guard (cockpit stopped + venv present) → backup touched files → copy payload → patch registration
#   (anchored, idempotent) → py_compile → copy tests → run tests.  Reversible: backups under <module>/backups.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-emotional-maturity"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-emotional-maturity apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

# 1. copy the maturity package and its tools
mkdir -p "$REPO_ROOT/src/sovereign_agent/maturity"
cp "$STAGING"/payload/src/sovereign_agent/maturity/*.py "$REPO_ROOT/src/sovereign_agent/maturity/"
cp "$STAGING/payload/src/sovereign_agent/tools/maturity_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"

# 2. register tools (anchored after engineering-playbook, idempotent)
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys; from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# maturity-import-d" in t:
    print("SKIP: tools/__init__.py already patched")
else:
    imp = "from .engineering_playbook_tools import EngineeringPlaybookTool  # engineering-playbook-import-d"
    allk = '    "EngineeringPlaybookTool",  # engineering-playbook-all-d'
    if imp not in t or allk not in t:
        sys.exit("APPLY-FAIL: engineering-playbook anchors not found in tools/__init__.py")
    t = t.replace(imp, imp + "\nfrom .maturity_tools import EmotionalCheckinTool, MaturityReportTool  # maturity-import-d", 1)
    t = t.replace(allk, allk + '\n    "EmotionalCheckinTool",  # maturity-all-d\n    "MaturityReportTool",  # maturity-all-d', 1)
    p.write_text(t); print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/maturity/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/maturity_tools.py" "$TOOLS_INIT" || \
  { echo "APPLY-FAIL: compile error — restoring tools/__init__.py"; cp "$BACKUP_DIR/tools_init.py.bak" "$TOOLS_INIT"; exit 1; }
# test file is named by PKG (new_module.sh writes test_<PKG>.py), NOT slug —
# they differ for every kebab-case slug, so referencing emotional-maturity here silently
# skipped the copy + ran pytest on a missing file (hardened 2026-07-19).
[[ -f "$STAGING/tests/test_maturity.py" ]] && cp "$STAGING/tests/test_maturity.py" "$REPO_ROOT/tests/"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_maturity.py -q || \
  { echo "APPLY-FAIL: applied tests did not pass — restoring tools/__init__.py"; cp "$BACKUP_DIR/tools_init.py.bak" "$TOOLS_INIT"; exit 1; }
echo "=== aria-emotional-maturity applied. Reversible: backups at $BACKUP_DIR 💛 ==="
