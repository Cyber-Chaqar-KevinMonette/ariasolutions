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

# 2. register tools (anchored + idempotent). v6.5+ layout: an isolated try/except block after
#    knowledge-maturity, so a broken import can never take the registry down. Falls back to the older
#    engineering-playbook anchor; refuses to guess if neither is present.
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys; from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# maturity-import-d" in t:
    print("SKIP: tools/__init__.py already patched"); sys.exit(0)
new_imp = ("try:  # tools-wired-d — maturity-d\n"
           "    from .maturity_tools import EmotionalCheckinTool, MaturityReportTool  # maturity-import-d\n"
           "except Exception:  # noqa: BLE001 - optional dep; keep the registry alive\n"
           "    EmotionalCheckinTool = MaturityReportTool = None  # type: ignore[assignment,misc]\n")
new_all = '    "EmotionalCheckinTool",  # maturity-all-d\n    "MaturityReportTool",  # maturity-all-d\n'
km_block = ("    KnowledgeMaturityTool = None  # type: ignore[assignment,misc]\n")
km_all = '    "KnowledgeMaturityTool",  # knowledge-maturity-d\n'
ep_imp = "from .engineering_playbook_tools import EngineeringPlaybookTool  # engineering-playbook-import-d\n"
ep_all = '    "EngineeringPlaybookTool",  # engineering-playbook-all-d\n'
if t.count(km_block) == 1 and t.count(km_all) == 1:
    t = t.replace(km_block, km_block + new_imp, 1).replace(km_all, km_all + new_all, 1)
elif t.count(ep_imp) == 1 and t.count(ep_all) == 1:
    t = t.replace(ep_imp, ep_imp + new_imp, 1).replace(ep_all, ep_all + new_all, 1)
else:
    sys.exit("APPLY-FAIL: no known anchor in tools/__init__.py (knowledge-maturity or engineering-playbook)")
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
