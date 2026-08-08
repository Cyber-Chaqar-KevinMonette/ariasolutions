#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_engineering_playbook.sh — index over wondelai/skills' software-
#  engineering frameworks (Clean Code, Refactoring Patterns, DDIA, System
#  Design, Clean Architecture, Release It!, Team Topologies, etc.)
#
#  Kevin pointed at github.com/wondelai/skills (MIT, 62 Claude Code skills
#  distilled from named books). Installed the marketplace (code-craftsmanship
#  + systems-architecture + metaskills plugins) in ~/.claude/settings.json for
#  direct slash-command use. This module is the companion move: an
#  Aria-internal INDEX (core principle + discipline names per skill, not a
#  reproduction) so Aria herself can recall and cite the right framework
#  unprompted when helping build sovereign-agent. Full depth is one
#  `Skill wondelai-skills:<slug>` invocation away.
#
#  Changes:
#    1. Install engineering_playbook.py (12-entry curated index)
#    2. Install tools/engineering_playbook_tools.py (EngineeringPlaybookTool, T0)
#    3. Patch tools/__init__.py — import + __all__ (markers: engineering-playbook-*)
#    4. Install tests/test_engineering_playbook.py
#
#  Idempotent. Backs up patched files.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
TOOLS="$PKG/tools"
INIT="$TOOLS/__init__.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install engineering_playbook.py ────────────────────────────────────
echo "→ installing engineering_playbook.py"
cp "$HERE/payload/src/sovereign_agent/engineering_playbook.py" "$PKG/engineering_playbook.py"
echo "  ✓ engineering_playbook.py"

# ── 2. Install tools/engineering_playbook_tools.py ────────────────────────
echo "→ installing tools/engineering_playbook_tools.py"
cp "$HERE/payload/src/sovereign_agent/tools/engineering_playbook_tools.py" \
   "$TOOLS/engineering_playbook_tools.py"
echo "  ✓ engineering_playbook_tools.py"

# ── 3. Patch tools/__init__.py ────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# engineering-playbook-import-d"
ALL_MARKER    = "# engineering-playbook-all-d"

if IMPORT_MARKER not in src:
    anchor = "from .business_playbook_tools import BusinessPlaybookTool  # business-playbook-import-d\n"
    if anchor in src:
        inject = (
            "from .engineering_playbook_tools import EngineeringPlaybookTool  " + IMPORT_MARKER + "\n"
        )
        src = src.replace(anchor, anchor + inject, 1)
        print("  ✓ engineering_playbook_tools import added")
    else:
        idx = src.find("__all__ = [")
        if idx >= 0:
            inject = "from .engineering_playbook_tools import EngineeringPlaybookTool  " + IMPORT_MARKER + "\n"
            src = src[:idx] + inject + src[idx:]
            print("  ✓ engineering_playbook_tools import added (fallback)")
        else:
            print("  ⚠ no anchor for import — manual edit required")
else:
    print("  ↷ engineering_playbook_tools import already present")

if ALL_MARKER not in src:
    anchor = '    "BusinessPlaybookTool",  # business-playbook-all-d\n'
    if anchor in src:
        inject = anchor + '    "EngineeringPlaybookTool",  ' + ALL_MARKER + "\n"
        src = src.replace(anchor, inject, 1)
        print("  ✓ EngineeringPlaybookTool added to __all__")
    else:
        print("  ⚠ BusinessPlaybookTool anchor not found in __all__ — skipping __all__ patch")
else:
    print("  ↷ EngineeringPlaybookTool already in __all__")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 4. Compile checks ─────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$PKG/engineering_playbook.py" "$TOOLS/engineering_playbook_tools.py" "$INIT"
echo "  ✓ all files compile"

cp "$HERE/tests/test_engineering_playbook.py" "$ROOT/tests/test_engineering_playbook.py"
python3 -m py_compile "$ROOT/tests/test_engineering_playbook.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. engineering_playbook tool is wired."
echo
echo "  engineering_playbook  (T0) — look up curated software-engineering framework"
echo "                               principles (index; invoke the real skill for full depth)"
echo
echo "  run: pytest tests/test_engineering_playbook.py -v"
