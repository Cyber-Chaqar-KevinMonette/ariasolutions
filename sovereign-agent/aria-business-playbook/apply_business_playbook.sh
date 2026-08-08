#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_business_playbook.sh — secular business/leadership/negotiation
#  reference frameworks, curated from a free coaching deck Kevin was given
#  (Ryan Blair's "Billion-Dollar Playbook," AlterCall). Religious content
#  (prayer, confession, oath-to-the-Creator, scripture) was deliberately
#  left out per explicit user direction — see business_playbook.py's
#  module docstring and README.md for the full inclusion/exclusion review.
#
#  This is reference knowledge, not doctrine: it does not touch
#  mos_canon.py or any values/behavior gate.
#
#  Changes:
#    1. Install business_playbook.py (the curated corpus + find_frameworks())
#    2. Install tools/business_playbook_tools.py (BusinessPlaybookTool, T0)
#    3. Patch tools/__init__.py — import + __all__ (markers: business-playbook-*)
#    4. Install tests/test_business_playbook.py
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

# ── 1. Install business_playbook.py ───────────────────────────────────────
echo "→ installing business_playbook.py"
cp "$HERE/payload/src/sovereign_agent/business_playbook.py" "$PKG/business_playbook.py"
echo "  ✓ business_playbook.py"

# ── 2. Install tools/business_playbook_tools.py ───────────────────────────
echo "→ installing tools/business_playbook_tools.py"
cp "$HERE/payload/src/sovereign_agent/tools/business_playbook_tools.py" \
   "$TOOLS/business_playbook_tools.py"
echo "  ✓ business_playbook_tools.py"

# ── 3. Patch tools/__init__.py ────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# business-playbook-import-d"
ALL_MARKER    = "# business-playbook-all-d"

if IMPORT_MARKER not in src:
    anchor = "from .award_movie_xp import AwardMovieXPTool  # movie-studio-d\n"
    if anchor in src:
        inject = (
            "from .business_playbook_tools import BusinessPlaybookTool  " + IMPORT_MARKER + "\n"
        )
        src = src.replace(anchor, anchor + inject, 1)
        print("  ✓ business_playbook_tools import added")
    else:
        idx = src.find("__all__ = [")
        if idx >= 0:
            inject = "from .business_playbook_tools import BusinessPlaybookTool  " + IMPORT_MARKER + "\n"
            src = src[:idx] + inject + src[idx:]
            print("  ✓ business_playbook_tools import added (fallback)")
        else:
            print("  ⚠ no anchor for import — manual edit required")
else:
    print("  ↷ business_playbook_tools import already present")

if ALL_MARKER not in src:
    anchor = '    "AwardMovieXPTool",  # movie-studio-d\n'
    if anchor in src:
        inject = anchor + '    "BusinessPlaybookTool",  ' + ALL_MARKER + "\n"
        src = src.replace(anchor, inject, 1)
        print("  ✓ BusinessPlaybookTool added to __all__")
    else:
        print("  ⚠ AwardMovieXPTool anchor not found in __all__ — skipping __all__ patch")
else:
    print("  ↷ BusinessPlaybookTool already in __all__")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 4. Compile checks ─────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$PKG/business_playbook.py" "$TOOLS/business_playbook_tools.py" "$INIT"
echo "  ✓ all files compile"

cp "$HERE/tests/test_business_playbook.py" "$ROOT/tests/test_business_playbook.py"
python3 -m py_compile "$ROOT/tests/test_business_playbook.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. business_playbook tool is wired."
echo
echo "  business_playbook  (T0) — look up curated secular business/leadership/"
echo "                            negotiation/communication frameworks"
echo
echo "  run: pytest tests/test_business_playbook.py -v"
